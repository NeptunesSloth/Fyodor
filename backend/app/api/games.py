"""Game rooms over REST and WebSocket."""

from __future__ import annotations

import json
import logging
import time
from typing import Annotated, Any, Literal

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, TypeAdapter, ValidationError, field_validator

from app.api.deps import _peer_is_loopback, get_services, is_local_request, require_local
from app.assistant import AssistantUnavailable, build_context
from app.decks import archidekt
from app.decks import service as deck_service
from app.decks.models import DeckEntry, DeckImportRequest
from app.decks.parser import DeckTextTooLarge
from app.decks.repository import DeckNotFound
from app.game.errors import ActionError
from app.game.factory import DeckCard, PlayerSetup, new_game
from app.game.mulligan import resolve_policy
from app.game.session import GameSession
from app.game.state import GameSettings, MulliganPolicy
from app.game.visibility import OMNISCIENT, SPECTATOR
from app.multiplayer.hub import Connection, Room
from app.multiplayer.lobby import DeckTooLarge, LobbySeatInfo, LobbySettings, SubmittedDeck, check_bounds
from app.services import Services
from app.storage.save_format import SaveFormatError
from app.storage.saves import SaveNotFound
from app.textutil import clean_text

log = logging.getLogger(__name__)
router = APIRouter(tags=["games"])
ServicesDep = Annotated[Services, Depends(get_services)]
MAX_WS_MESSAGE = 64 * 1024

# --------------------------------------------------------------------------- access control


VIEWER_ALIASES = {"all": OMNISCIENT, "spectator": SPECTATOR}


def authorize(room: Room, *, local: bool, token: str | None, viewer: str | None, as_player: str | None) -> tuple[str, str | None]:
    """Return (viewer, actor) for a request, or raise HTTPException."""
    if room.mode == "local":
        if not local:
            raise HTTPException(403, "This is a hot-seat game on the host computer")
        v = VIEWER_ALIASES.get(viewer or "", viewer) or room.session.state.seat_order[0]
        if v not in room.seats and v not in (SPECTATOR, OMNISCIENT):
            raise HTTPException(400, "Unknown viewer")
        actor = as_player or (v if v in room.seats else room.session.state.turn.active_player)
        if actor not in room.seats:
            raise HTTPException(400, "Unknown player")
        return v, actor
    seat = room.seat_for_token(token)
    if seat is None:
        if local and room.is_host(token):
            return OMNISCIENT if viewer == "all" else SPECTATOR, None
        raise HTTPException(403, "Join the game first (missing or invalid seat token)")
    return seat, (seat if seat != SPECTATOR else None)


HOST_ONLY_ACTIONS = {"mulligan_finish"}


def _check_host_only(room: Room, action: dict[str, Any], *, host: bool) -> None:
    """Some actions are table-level overrides only the host may use (anyone at a hot-seat table)."""
    if action.get("type") in HOST_ONLY_ACTIONS and room.mode == "lan" and not host:
        raise HTTPException(403, "Only the host can do that")


def _room(services: Services, game_id: str) -> Room:
    room = services.hub.get(game_id)
    if room is None:
        raise HTTPException(404, "Game not found (it may have been closed; load it from Saves)")
    return room


# --------------------------------------------------------------------------- models


class PlayerIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    deck_id: str | None = Field(default=None, max_length=64)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")

    @field_validator("name")
    @classmethod
    def _clean(cls, v: str) -> str:
        cleaned = clean_text(v, 40)
        if not cleaned:
            raise ValueError("name must not be blank")
        return cleaned


class CreateGameIn(BaseModel):
    name: str = Field(default="Game", max_length=80)
    format: Literal["commander", "constructed", "sandbox"] = "commander"
    mode: Literal["local", "lan"] = "local"
    password: str | None = Field(default=None, max_length=100)
    players: list[PlayerIn] = Field(default_factory=list, max_length=6)
    shuffle: bool = True
    first_player: int | Literal["random"] | None = None
    starting_life: int | None = Field(default=None, ge=1, le=10000)
    auto_untap: bool = True
    host_seat: str | None = Field(default="p1", max_length=8)
    # LAN lobby: players take seats and choose their own decks before the host starts.
    lobby: bool = False
    seats: int = Field(default=4, ge=1, le=6)
    deck_privacy: Literal["private", "commander_only", "public"] = "commander_only"
    # Guided opening hands: "commander_london", "london", "boston_custom", "custom" or "none".
    # Unset: lobbies use the format's usual rule; hot-seat games deal no hands (sandbox).
    mulligan_rule: str | None = Field(default=None, max_length=40)
    mulligan_policy: MulliganPolicy | None = None  # fields for boston_custom / custom
    priority_helper: Literal["off", "simple"] = "simple"

    @field_validator("name")
    @classmethod
    def _clean(cls, v: str) -> str:
        return clean_text(v, 80) or "Game"


class ActionIn(BaseModel):
    action: dict[str, Any]
    as_player: str | None = Field(default=None, alias="as", max_length=16)
    viewer: str | None = Field(default=None, max_length=32)


class MetaIn(BaseModel):
    as_player: str | None = Field(default=None, alias="as", max_length=16)
    viewer: str | None = Field(default=None, max_length=32)


class JoinIn(BaseModel):
    code: str = Field(min_length=4, max_length=12)
    name: str | None = Field(default=None, max_length=40)
    password: str | None = Field(default=None, max_length=100)
    seat: str | None = Field(default=None, max_length=8)
    spectate: bool = False


class SaveIn(BaseModel):
    name: str = Field(default="", max_length=80)


class LoadIn(BaseModel):
    mode: Literal["local", "lan"] = "local"
    password: str | None = Field(default=None, max_length=100)


# --------------------------------------------------------------------------- helpers


def _setup_players(services: Services, body: CreateGameIn) -> list[PlayerSetup]:
    setups = []
    for p in body.players:
        if not p.deck_id:
            setups.append(PlayerSetup(name=p.name, color=p.color))
            continue
        try:
            deck = services.decks.get(p.deck_id)
        except DeckNotFound:
            raise HTTPException(404, f"Deck not found for {p.name}") from None
        entries, _ = deck_service.reconcile_entries(deck.entries, services.cards)
        cards = _deck_cards(services, entries)
        setups.append(PlayerSetup(name=p.name, deck_id=deck.id, deck_name=deck.name, cards=cards, color=p.color))
    return setups


def _deck_cards(services: Services, entries: list[DeckEntry]) -> list[DeckCard]:
    names = services.cards.get_many([e.printing_id for e in entries if e.printing_id])
    return [
        DeckCard(e.section, e.quantity, names[e.printing_id]["name"] if e.printing_id in names else e.name,
                 e.printing_id if e.printing_id in names else None, categories=list(e.categories))
        for e in entries
    ]


def _create_lobby(services: Services, body: CreateGameIn) -> dict[str, Any]:
    if body.mode != "lan":
        raise HTTPException(422, "A lobby is for LAN games")
    settings = LobbySettings(name=body.name, format=body.format, seats=body.seats, starting_life=body.starting_life,
                             deck_privacy=body.deck_privacy,
                             mulligan_rule=body.mulligan_rule or ("commander_london" if body.format == "commander" else "london"),
                             mulligan_policy=body.mulligan_policy, priority_helper=body.priority_helper,
                             auto_untap=body.auto_untap)
    room = services.hub.create_lobby(settings, password=body.password)
    result: dict[str, Any] = {"game": room.summary(), "host_token": room.host_token}
    if body.host_seat:
        host_name = body.players[0].name if body.players else None
        viewer, token = services.hub.claim_seat(room, name=host_name, seat=body.host_seat if body.host_seat in room.seats else None)
        room.host_seat = viewer
        result["seat"] = {"player_id": viewer, "token": token}
    return result


def _create_room(services: Services, session: GameSession, mode: str, password: str | None,
                 host_seat: str | None) -> dict[str, Any]:
    room = services.hub.create_room(session, mode=mode, password=password)  # type: ignore[arg-type]
    result: dict[str, Any] = {"game": room.summary(), "host_token": room.host_token}
    if mode == "lan" and host_seat:
        viewer, token = services.hub.claim_seat(room, name=None, seat=host_seat if host_seat in room.seats else None)
        room.host_seat = viewer
        result["seat"] = {"player_id": viewer, "token": token}
    services.autosave(room)
    return result


# --------------------------------------------------------------------------- REST


@router.get("/games")
def list_games(request: Request, services: ServicesDep) -> list[dict[str, Any]]:
    local = is_local_request(request)
    return [r.summary() for r in services.hub.rooms.values() if local or r.mode == "lan"]


@router.post("/games", status_code=201)
def create_game(body: CreateGameIn, request: Request, services: ServicesDep) -> dict[str, Any]:
    require_local(request)
    if body.lobby:
        return _create_lobby(services, body)
    if not body.players:
        raise HTTPException(422, "A game needs at least one player")
    setups = _setup_players(services, body)
    first = None
    if body.first_player == "random":
        import secrets

        first = secrets.randbelow(len(setups))
    elif isinstance(body.first_player, int):
        first = body.first_player
    try:
        policy = resolve_policy(body.mulligan_rule, body.mulligan_policy) if body.mulligan_rule else None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if policy is not None and policy.needs_definition:
        raise HTTPException(422, f"Define the {policy.display_name} mulligan first (or pick another rule)")
    settings = GameSettings(starting_life=body.starting_life or {"commander": 40}.get(body.format, 20), auto_untap=body.auto_untap,
                            deck_privacy=body.deck_privacy, priority_helper=body.priority_helper, mulligan=policy)
    state = new_game(setups, name=body.name, format=body.format, settings=settings, shuffle=body.shuffle, first_player=first)
    session = GameSession(state, cards=services.cards, history_limit=services.settings.history_limit, rules=services.rules)
    session.notice(f"Game created. {state.players[state.turn.active_player].name} goes first.")
    return _create_room(services, session, body.mode, body.password, body.host_seat)


@router.get("/games/{game_id}")
def game_summary(game_id: str, services: ServicesDep) -> dict[str, Any]:
    room = _room(services, game_id)
    return room.summary()


@router.get("/games/{game_id}/view")
def game_view(
    game_id: str,
    request: Request,
    services: ServicesDep,
    viewer: Annotated[str | None, Query(max_length=32)] = None,
    x_seat_token: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    room = _room(services, game_id)
    v, _ = authorize(room, local=is_local_request(request), token=x_seat_token, viewer=viewer, as_player=None)
    return services.hub.view(room, v)


@router.post("/games/{game_id}/actions")
async def post_action(
    game_id: str, body: ActionIn, request: Request, services: ServicesDep, x_seat_token: Annotated[str | None, Header()] = None
) -> dict[str, Any]:
    room = _room(services, game_id)
    viewer, actor = authorize(room, local=is_local_request(request), token=x_seat_token, viewer=body.viewer, as_player=body.as_player)
    if actor is None:
        raise HTTPException(403, "Spectators cannot act")
    _check_host_only(room, body.action, host=room.is_host(x_seat_token))
    async with room.lock:
        try:
            room.session.perform(actor, body.action)
        except ValidationError as exc:
            raise HTTPException(422, _validation_message(exc)) from exc
        except ActionError as exc:
            raise HTTPException(409, str(exc)) from exc
        services.hub.after_change(room)
    await services.hub.broadcast(room)
    return services.hub.view(room, viewer)


@router.post("/games/{game_id}/undo")
async def undo(game_id: str, body: MetaIn, request: Request, services: ServicesDep,
               x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    return await _history_op(services, game_id, body, request, x_seat_token, "undo")


@router.post("/games/{game_id}/redo")
async def redo(game_id: str, body: MetaIn, request: Request, services: ServicesDep,
               x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    return await _history_op(services, game_id, body, request, x_seat_token, "redo")


async def _history_op(services: Services, game_id: str, body: MetaIn, request: Request, token: str | None, op: str) -> dict[str, Any]:
    room = _room(services, game_id)
    viewer, actor = authorize(room, local=is_local_request(request), token=token, viewer=body.viewer, as_player=body.as_player)
    if actor is None:
        raise HTTPException(403, "Spectators cannot undo")
    async with room.lock:
        try:
            room.session.undo(actor) if op == "undo" else room.session.redo(actor)
        except ActionError as exc:
            raise HTTPException(409, str(exc)) from exc
        services.hub.after_change(room)
    await services.hub.broadcast(room)
    return services.hub.view(room, viewer)


@router.post("/games/{game_id}/save", status_code=201)
async def save_game(game_id: str, body: SaveIn, request: Request, services: ServicesDep,
                    x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    room = _room(services, game_id)
    authorize(room, local=is_local_request(request), token=x_seat_token, viewer=None, as_player=None)
    name = clean_text(body.name, 80) or f"{room.session.state.name} — turn {room.session.state.turn.number}"
    async with room.lock:
        summary = services.saves.save(room.session.state, room.session.history, name=name)
        room.session.notice(f"Game saved as “{name}”.")
    await services.hub.broadcast(room)
    return summary


@router.delete("/games/{game_id}", status_code=204)
async def close_game(game_id: str, request: Request, services: ServicesDep) -> Response:
    require_local(request)
    room = _room(services, game_id)
    async with room.lock:
        services.autosave(room)
        for conn in list(room.connections.values()):
            try:
                await conn.send({"type": "closed"})
            except Exception:  # noqa: BLE001 - best effort notification
                log.debug("could not notify %s", conn.id)
        services.hub.close(game_id)
    return Response(status_code=204)


def client_ip(request: Request) -> str:
    host = request.client.host if request.client else "?"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and _peer_is_loopback(host, None):
        return forwarded.split(",")[0].strip()
    return host


def _throttle_join(failures: dict[str, list[float]], ip: str) -> None:
    now = time.monotonic()
    recent = [t for t in failures.get(ip, []) if now - t < 60]
    failures[ip] = recent
    if len(recent) >= 10:
        raise HTTPException(429, "Too many failed join attempts; wait a minute")


@router.post("/join")
def join_game(body: JoinIn, request: Request, services: ServicesDep) -> dict[str, Any]:
    ip = client_ip(request)
    failures = services.hub.join_failures
    _throttle_join(failures, ip)
    room = services.hub.by_code(body.code)
    if room is None or not room.check_password(body.password):
        failures.setdefault(ip, []).append(time.monotonic())
        raise HTTPException(403, "Unknown room code or wrong password")
    name = clean_text(body.name or "", 40) or None
    try:
        viewer, token = services.hub.claim_seat(room, name=name, seat=body.seat, spectate=body.spectate)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(409, str(exc)) from exc
    if name and viewer in room.seats and room.started:
        room.session.notice(f"{name} took the seat of {room.session.state.players[viewer].name}.")
        try:
            room.session.perform(viewer, {"type": "rename_player", "name": name})
        except (ActionError, ValidationError) as exc:
            log.info("Could not apply joining player's name: %s", exc)
    return {"game_id": room.id, "viewer": viewer, "token": token, "game": room.summary()}


@router.get("/saves")
def list_saves(request: Request, services: ServicesDep) -> list[dict[str, Any]]:
    require_local(request)
    return services.saves.list_all()


@router.post("/saves/{save_id}/load", status_code=201)
def load_save(save_id: str, body: LoadIn, request: Request, services: ServicesDep) -> dict[str, Any]:
    require_local(request)
    try:
        state, history = services.saves.load(save_id, history_limit=services.settings.history_limit)
    except SaveNotFound:
        raise HTTPException(404, "Save not found") from None
    except SaveFormatError as exc:
        raise HTTPException(422, str(exc)) from exc
    existing = services.hub.get(state.id)
    if existing is not None:
        services.hub.close(state.id)
    session = GameSession(state, cards=services.cards, history=history, history_limit=services.settings.history_limit,
                          rules=services.rules)
    session.notice("Game loaded.")
    return _create_room(services, session, body.mode, body.password, "p1")


@router.delete("/saves/{save_id}", status_code=204)
def delete_save(save_id: str, request: Request, services: ServicesDep) -> Response:
    require_local(request)
    try:
        services.saves.delete(save_id)
    except SaveNotFound:
        raise HTTPException(404, "Save not found") from None
    return Response(status_code=204)


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    viewer: str | None = Field(default=None, max_length=32)


@router.post("/games/{game_id}/assistant")
def ask_assistant(game_id: str, body: AskIn, request: Request, services: ServicesDep,
                  x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Ask the optional local rules assistant. It sees only the asking player's view."""
    if services.assistant is None:
        raise HTTPException(404, "The rules assistant is disabled (set FYODOR_ASSISTANT_URL to enable it)")
    room = _room(services, game_id)
    viewer, _ = authorize(room, local=is_local_request(request), token=x_seat_token, viewer=body.viewer, as_player=None)
    if viewer == OMNISCIENT:
        viewer = room.session.state.turn.active_player
    context = build_context(services.hub.view(room, viewer), services.cards)
    try:
        answer = services.assistant.ask(clean_text(body.question, 1000, multiline=True), context)
    except AssistantUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"answer": answer}


@router.get("/lan-info")
def lan_info(request: Request, services: ServicesDep) -> dict[str, Any]:
    require_local(request)
    import socket

    addresses: set[str] = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # no packets are sent; picks the LAN interface
            addresses.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addresses.add(str(info[4][0]))
    except OSError:
        pass
    lan = sorted(a for a in addresses if not a.startswith("127."))
    return {
        "addresses": lan,
        "port": services.settings.port,
        "bound_host": services.settings.host,
        "reachable": services.settings.host not in ("127.0.0.1", "localhost", "::1"),
    }


def _validation_message(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "Invalid action"
    loc = ".".join(str(p) for p in errors[0]["loc"])
    return f"Invalid action: {errors[0]['msg']}" + (f" ({loc})" if loc else "")


# --------------------------------------------------------------------------- lobby


class LobbyDeckIn(BaseModel):
    """A deck a player brings to the table. Content only: never a file path."""

    name: str | None = Field(default=None, max_length=120)
    text: str = Field(default="", max_length=200_000)
    archidekt: str | None = Field(default=None, max_length=300)
    json_data: str | None = Field(default=None, max_length=2_000_000, alias="json")
    deck_id: str | None = Field(
        default=None, max_length=64
    )  # a deck in the host's library (host computer only)

    model_config = {"populate_by_name": True}


class ReadyIn(BaseModel):
    ready: bool = True


class SeatIn(BaseModel):
    seat: str = Field(pattern=r"^p[1-6]$")


class ProfileIn(BaseModel):
    name: str | None = Field(default=None, max_length=40)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class LobbySettingsIn(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    format: Literal["commander", "constructed", "sandbox"] | None = None
    seats: int | None = Field(default=None, ge=1, le=6)
    starting_life: int | None = Field(default=None, ge=1, le=10000)
    deck_privacy: Literal["private", "commander_only", "public"] | None = None
    mulligan_rule: str | None = Field(default=None, max_length=40)
    mulligan_policy: MulliganPolicy | None = None
    priority_helper: Literal["off", "simple"] | None = None
    auto_untap: bool | None = None


class StartIn(BaseModel):
    force: bool = False  # host override: start although not everyone is ready
    shuffle: bool = True
    first_player: Literal["random"] | int | None = "random"


ARCHIDEKT_COOLDOWN = 3.0


def _lobby_room(services: Services, game_id: str) -> Room:
    room = _room(services, game_id)
    if room.started:
        raise HTTPException(409, "The game has already started")
    return room


def _lobby_who(room: Room, token: str | None, *, seat_required: bool = True) -> tuple[str, bool]:
    """(viewer, is_host) for a lobby request."""
    seat = room.seat_for_token(token)
    host = room.is_host(token)
    if seat is None:
        if host:
            return SPECTATOR, True
        raise HTTPException(403, "Join the game first (missing or invalid seat token)")
    if seat_required and seat == SPECTATOR:
        raise HTTPException(403, "Spectators don't have a seat")
    return seat, host


def _require_host(room: Room, token: str | None) -> None:
    if not room.is_host(token):
        raise HTTPException(403, "Only the host can do that")


async def _lobby_changed(services: Services, room: Room) -> None:
    await services.hub.broadcast(room)


def _lobby_response(room: Room, viewer: str, host: bool) -> dict[str, Any]:
    return room.lobby_view(viewer, host=host)


@router.get("/games/{game_id}/lobby")
def get_lobby(
    game_id: str, services: ServicesDep, x_seat_token: Annotated[str | None, Header()] = None
) -> dict[str, Any]:
    room = _room(services, game_id)
    if room.started:
        return {"phase": "playing", "game": room.summary()}
    viewer, host = _lobby_who(room, x_seat_token, seat_required=False)
    return _lobby_response(room, viewer, host)


def _submitted(
    services: Services,
    entries: list[DeckEntry],
    *,
    name: str,
    fmt: str | None,
    report: dict[str, Any],
    kind: str,
) -> SubmittedDeck:
    cards = _deck_cards(services, entries)
    check_bounds(cards)
    commander_ids = [c.printing_id for c in cards if c.section == "commander" and c.printing_id]
    data = services.cards.get_many(commander_ids) if commander_ids else {}
    identity = sorted(
        {x for d in data.values() for x in d.get("color_identity") or []}, key=lambda c: "WUBRG".find(c)
    )
    return SubmittedDeck(
        name=clean_text(name, 120) or "Deck",
        cards=cards,
        commanders=[c.name for c in cards if c.section == "commander"],
        color_identity=identity,
        card_count=sum(c.quantity for c in cards if c.section in ("main", "commander", "companion")),
        format=fmt,
        report=report,
        source_kind=kind,
    )


def _import_for_lobby(services: Services, body: LobbyDeckIn, local: bool) -> SubmittedDeck:
    if body.deck_id:
        if not local:
            raise HTTPException(403, "The host's deck library is only available on the host computer")
        try:
            deck = services.decks.get(body.deck_id)
        except DeckNotFound:
            raise HTTPException(404, "Deck not found") from None
        entries, notes = deck_service.reconcile_entries(deck.entries, services.cards)
        unresolved = [e.name for e in entries if not e.printing_id]
        report = {
            "cards_total": sum(e.quantity for e in entries if e.section != "maybeboard"),
            "unresolved": [{"line": n} for n in unresolved[:50]],
            "notes": notes[:20],
        }
        return _submitted(
            services, entries, name=body.name or deck.name, fmt=deck.format, report=report, kind="library"
        )
    if not (body.text.strip() or body.archidekt or body.json_data):
        raise HTTPException(422, "Paste a deck list, give an Archidekt URL, or choose a file")
    req = DeckImportRequest(text=body.text, archidekt=body.archidekt, json=body.json_data)
    try:
        result = deck_service.import_any(
            req, services.cards, fetch=services.archidekt_fetch if services.settings.allow_network else None
        )
    except DeckTextTooLarge as exc:
        raise HTTPException(413, str(exc)) from exc
    except archidekt.ArchidektError as exc:
        raise HTTPException(502 if body.archidekt else 422, str(exc)) from exc
    full = result.report.as_dict()
    report = {
        k: full[k] for k in ("cards_total", "exact_printings", "resolved", "commanders", "errors", "notes")
    }
    report["unresolved"] = full["unresolved"][:50]
    kind = "archidekt" if result.source else "text"
    if not any(e.printing_id for e in result.entries):
        raise HTTPException(422, "No known cards found in that deck (check the list or update the card database)")
    return _submitted(
        services,
        result.entries,
        name=body.name or result.parsed.name or "Deck",
        fmt=result.format,
        report=report,
        kind=kind,
    )


@router.post("/games/{game_id}/lobby/deck")
async def submit_deck(
    game_id: str,
    body: LobbyDeckIn,
    request: Request,
    services: ServicesDep,
    x_seat_token: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Choose your own deck. The host parses and resolves it against its own card database."""
    room = _lobby_room(services, game_id)
    viewer, host = _lobby_who(room, x_seat_token)
    info = room.lobby_seats.setdefault(viewer, LobbySeatInfo())
    if body.archidekt:
        now = time.monotonic()
        if now - info.last_fetch < ARCHIDEKT_COOLDOWN:
            raise HTTPException(429, "Wait a moment before fetching another deck")
        info.last_fetch = now
    try:
        deck = await run_in_threadpool(_import_for_lobby, services, body, is_local_request(request))
    except DeckTooLarge as exc:
        raise HTTPException(413, str(exc)) from exc
    async with room.lock:
        if room.started or room.seat_for_token(x_seat_token) != viewer:
            raise HTTPException(409, "Your seat changed while the deck was loading")
        info = room.lobby_seats.setdefault(viewer, LobbySeatInfo())
        info.deck = deck
        info.ready = False
    await _lobby_changed(services, room)
    return _lobby_response(room, viewer, host)


@router.delete("/games/{game_id}/lobby/deck")
async def clear_deck(
    game_id: str, services: ServicesDep, x_seat_token: Annotated[str | None, Header()] = None
) -> dict[str, Any]:
    room = _lobby_room(services, game_id)
    viewer, host = _lobby_who(room, x_seat_token)
    info = room.lobby_seats.setdefault(viewer, LobbySeatInfo())
    info.deck, info.ready = None, False
    await _lobby_changed(services, room)
    return _lobby_response(room, viewer, host)


@router.post("/games/{game_id}/lobby/ready")
async def set_ready(
    game_id: str, body: ReadyIn, services: ServicesDep, x_seat_token: Annotated[str | None, Header()] = None
) -> dict[str, Any]:
    room = _lobby_room(services, game_id)
    viewer, host = _lobby_who(room, x_seat_token)
    info = room.lobby_seats.setdefault(viewer, LobbySeatInfo())
    if body.ready and info.deck is None:
        raise HTTPException(409, "Choose a deck first")
    info.ready = body.ready
    await _lobby_changed(services, room)
    return _lobby_response(room, viewer, host)


@router.post("/games/{game_id}/lobby/seat")
async def change_seat(
    game_id: str, body: SeatIn, services: ServicesDep, x_seat_token: Annotated[str | None, Header()] = None
) -> dict[str, Any]:
    room = _lobby_room(services, game_id)
    viewer, host = _lobby_who(room, x_seat_token)
    if body.seat != viewer:
        try:
            services.hub.move_seat(room, viewer, body.seat)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(409, str(exc)) from exc
    await _lobby_changed(services, room)
    return _lobby_response(room, body.seat, host)


@router.post("/games/{game_id}/lobby/profile")
async def set_profile(
    game_id: str, body: ProfileIn, services: ServicesDep, x_seat_token: Annotated[str | None, Header()] = None
) -> dict[str, Any]:
    room = _lobby_room(services, game_id)
    viewer, host = _lobby_who(room, x_seat_token)
    info = room.lobby_seats.setdefault(viewer, LobbySeatInfo())
    if body.name is not None:
        name = clean_text(body.name, 40)
        if not name:
            raise HTTPException(422, "Name must not be blank")
        info.name = name
        room.seats[viewer].claimed_name = name
    if body.color is not None:
        info.color = body.color
    await _lobby_changed(services, room)
    return _lobby_response(room, viewer, host)


@router.post("/games/{game_id}/lobby/leave", status_code=204)
async def leave_lobby(
    game_id: str, services: ServicesDep, x_seat_token: Annotated[str | None, Header()] = None
) -> Response:
    room = _lobby_room(services, game_id)
    viewer, _ = _lobby_who(room, x_seat_token)
    if viewer == room.host_seat:
        raise HTTPException(409, "The host can't leave their own table (close the game instead)")
    services.hub.release_seat(room, viewer)
    await _lobby_changed(services, room)
    return Response(status_code=204)


@router.post("/games/{game_id}/lobby/settings")
async def lobby_settings(
    game_id: str,
    body: LobbySettingsIn,
    services: ServicesDep,
    x_seat_token: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    room = _lobby_room(services, game_id)
    _require_host(room, x_seat_token)
    viewer, host = _lobby_who(room, x_seat_token, seat_required=False)
    current = room.lobby or LobbySettings()
    patch = body.model_dump(exclude_none=True)
    try:
        updated = LobbySettings(**{**current.model_dump(), **patch})
    except ValidationError as exc:
        raise HTTPException(422, _validation_message(exc)) from exc
    if updated.seats != current.seats:
        try:
            services.hub.resize_lobby(room, updated.seats)
        except PermissionError as exc:
            raise HTTPException(409, str(exc)) from exc
    # Changing the rules of the game means everyone confirms again.
    if any(
        getattr(updated, k) != getattr(current, k)
        for k in ("format", "starting_life", "mulligan_rule", "mulligan_policy", "deck_privacy")
    ):
        for info in room.lobby_seats.values():
            info.ready = False
    room.lobby = updated
    await _lobby_changed(services, room)
    return _lobby_response(room, viewer, host)


@router.post("/games/{game_id}/lobby/kick")
async def kick_player(
    game_id: str, body: SeatIn, services: ServicesDep, x_seat_token: Annotated[str | None, Header()] = None
) -> dict[str, Any]:
    room = _lobby_room(services, game_id)
    _require_host(room, x_seat_token)
    viewer, host = _lobby_who(room, x_seat_token, seat_required=False)
    if body.seat not in room.seats:
        raise HTTPException(404, "No such seat")
    if body.seat == room.host_seat:
        raise HTTPException(409, "You can't kick yourself")
    await services.hub.send_to(room, body.seat, {"type": "kicked"})
    for conn in [c for c in room.connections.values() if c.viewer == body.seat]:
        conn.viewer, conn.actor = SPECTATOR, None
    services.hub.release_seat(room, body.seat)
    room.seats[body.seat].connections = 0
    await _lobby_changed(services, room)
    return _lobby_response(room, viewer, host)


@router.post("/games/{game_id}/lobby/start")
async def start_game(
    game_id: str, body: StartIn, services: ServicesDep, x_seat_token: Annotated[str | None, Header()] = None
) -> dict[str, Any]:
    room = _lobby_room(services, game_id)
    _require_host(room, x_seat_token)
    async with room.lock:
        if room.started:
            raise HTTPException(409, "The game has already started")
        blockers = room.start_blockers()
        order = [pid for pid, seat in room.seats.items() if seat.token is not None]
        if not order:
            raise HTTPException(409, "Nobody has taken a seat")
        if blockers and not body.force:
            raise HTTPException(409, "Not everyone is ready: " + "; ".join(blockers))
        lobby = room.lobby or LobbySettings()
        setups = []
        for pid in order:
            info = room.lobby_seats.get(pid) or LobbySeatInfo()
            deck = info.deck
            setups.append(
                PlayerSetup(
                    name=room.seat_name(pid),
                    color=info.color,
                    deck_name=deck.name if deck else None,
                    cards=list(deck.cards) if deck else [],
                )
            )
        first: int | None = None
        if body.first_player == "random":
            import secrets

            first = secrets.randbelow(len(setups))
        elif isinstance(body.first_player, int):
            first = body.first_player if 0 <= body.first_player < len(setups) else 0
        settings = GameSettings(
            starting_life=lobby.starting_life or {"commander": 40}.get(lobby.format, 20),
            auto_untap=lobby.auto_untap,
            deck_privacy=lobby.deck_privacy,
            priority_helper=lobby.priority_helper,
            mulligan=lobby.policy(),
        )
        state = new_game(
            setups,
            name=lobby.name,
            format=lobby.format,
            settings=settings,
            shuffle=body.shuffle,
            first_player=first,
        )
        state.id = room.game_id  # same URL before and after the start
        session = GameSession(
            state, cards=services.cards, history_limit=services.settings.history_limit, rules=services.rules
        )
        session.notice(f"Game started. {state.players[state.turn.active_player].name} goes first.")
        if blockers:
            session.notice("The host started without waiting for everyone.")
        services.hub.start(room, session, order)
        services.autosave(room)
    await services.hub.broadcast(room)
    return {"game": room.summary(), "seats": {pid: pid for pid in room.seats}}


# --------------------------------------------------------------------------- WebSocket


class WsAction(BaseModel):
    type: Literal["action"]
    action: dict[str, Any]
    as_player: str | None = Field(default=None, alias="as", max_length=16)
    id: int | None = None


class WsSimple(BaseModel):
    type: Literal["undo", "redo", "ping", "view"]
    as_player: str | None = Field(default=None, alias="as", max_length=16)
    viewer: str | None = Field(default=None, max_length=32)
    id: int | None = None


WS_MESSAGE: TypeAdapter[WsAction | WsSimple] = TypeAdapter(WsAction | WsSimple)


class _RateLimiter:
    def __init__(self, rate: float = 25.0, burst: float = 60.0) -> None:
        self.rate, self.burst, self.tokens, self.last = rate, burst, burst, time.monotonic()

    def allow(self) -> bool:
        now = time.monotonic()
        self.tokens = min(self.burst, self.tokens + (now - self.last) * self.rate)
        self.last = now
        if self.tokens < 1:
            return False
        self.tokens -= 1
        return True


async def game_socket(websocket: WebSocket, game_id: str) -> None:
    services: Services = websocket.app.state.services
    room = services.hub.get(game_id)
    if room is None:
        await websocket.close(code=4404, reason="Game not found")
        return
    params = websocket.query_params
    try:
        viewer, actor = authorize(room, local=is_local_request(websocket), token=params.get("token"),
                                  viewer=params.get("viewer"), as_player=None)
    except HTTPException as exc:
        await websocket.close(code=4403, reason=str(exc.detail))
        return
    await websocket.accept()

    async def send(message: dict[str, Any]) -> None:
        await websocket.send_text(json.dumps(message, separators=(",", ":")))

    conn = Connection(viewer=viewer, send=send, actor=actor, host=room.is_host(params.get("token")))
    services.hub.connect(room, conn)
    limiter = _RateLimiter()
    try:
        await send(services.hub.message(room, viewer, host=conn.host))
        await services.hub.broadcast(room)  # others see the connection indicator
        while True:
            raw = await websocket.receive_text()
            if len(raw) > MAX_WS_MESSAGE:
                await send({"type": "error", "message": "Message too large"})
                continue
            if not limiter.allow():
                await send({"type": "error", "message": "Slow down"})
                continue
            await _handle_ws_message(services, room, conn, raw, send)
    except WebSocketDisconnect:
        pass
    finally:
        services.hub.disconnect(room, conn)
        if services.hub.get(game_id) is room:
            await services.hub.broadcast(room)


async def _handle_ws_message(services: Services, room: Room, conn: Connection, raw: str, send: Any) -> None:
    try:
        msg = WS_MESSAGE.validate_json(raw)
    except ValidationError:
        await send({"type": "error", "message": "Malformed message"})
        return
    if msg.type == "ping":
        await send({"type": "pong", "id": msg.id})
        return
    if not room.started:
        await send({"type": "error", "id": msg.id, "message": "The game hasn't started yet"})
        return
    if msg.type == "view":
        if room.mode != "local":
            await send({"type": "error", "id": msg.id, "message": "Cannot change seats in a LAN game"})
            return
        new_viewer = VIEWER_ALIASES.get(msg.viewer or "", msg.viewer) or conn.viewer
        if new_viewer not in room.seats and new_viewer not in (SPECTATOR, OMNISCIENT):
            await send({"type": "error", "id": msg.id, "message": "Unknown viewer"})
            return
        services.hub.disconnect(room, conn)
        conn.viewer = new_viewer
        conn.actor = new_viewer if new_viewer in room.seats else conn.actor
        services.hub.connect(room, conn)
        await send({"type": "state", "view": services.hub.view(room, conn.viewer)})
        return
    actor = conn.actor
    if room.mode == "local" and msg.as_player:
        actor = msg.as_player if msg.as_player in room.seats else None
    elif room.mode == "local" and actor is None:
        actor = room.session.state.turn.active_player
    if actor is None:
        await send({"type": "error", "id": msg.id, "message": "Spectators cannot act"})
        return
    if isinstance(msg, WsAction):
        try:
            _check_host_only(room, msg.action, host=conn.host)
        except HTTPException as exc:
            await send({"type": "error", "id": msg.id, "message": str(exc.detail)})
            return
    async with room.lock:
        try:
            if isinstance(msg, WsAction):
                room.session.perform(actor, msg.action)
            elif msg.type == "undo":
                room.session.undo(actor)
            else:
                room.session.redo(actor)
        except ValidationError as exc:
            await send({"type": "error", "id": msg.id, "message": _validation_message(exc)})
            return
        except ActionError as exc:
            await send({"type": "error", "id": msg.id, "message": str(exc)})
            return
        services.hub.after_change(room)
    await send({"type": "ack", "id": msg.id})
    await services.hub.broadcast(room)
