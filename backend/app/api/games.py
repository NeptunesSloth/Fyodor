"""Game rooms over REST and WebSocket."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from collections.abc import Callable
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
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

from app.api.deps import _peer_is_loopback, get_services, is_local_request, require_local
from app.assets.store import AssetNotFound
from app.assistant import AssistantUnavailable, build_context
from app.cards.repository import CardDatabaseUnavailable
from app.decks import archidekt, sites
from app.decks import service as deck_service
from app.decks.models import DeckEntry, DeckImportRequest, DeckIn
from app.decks.parser import DeckTextTooLarge, format_deck_text
from app.decks.repository import DeckNotFound
from app.game import actions as A
from app.game import placement, undo_requests
from app.game.errors import ActionError
from app.game.factory import STARTING_LIFE, DeckCard, PlayerSetup, new_game
from app.game.handlers import planechase
from app.game.mulligan import resolve_policy
from app.game.rules_state import AUTOMATION_PRESETS, AutomationLevel, start_rules
from app.game.session import GameSession
from app.game.state import CollectionCard, GameSettings, MulliganPolicy, PlanarCard
from app.game.views import build_view
from app.game.visibility import OMNISCIENT, SPECTATOR, publicly_visible
from app.multiplayer import lan_art
from app.multiplayer.hub import RECONNECT_GRACE, Connection, Room, undo_voters
from app.multiplayer.lobby import (
    CardPermissions,
    DeckTooLarge,
    LobbySeatInfo,
    LobbySettings,
    SubmittedDeck,
    TableFormat,
    TurnOrder,
    check_bounds,
)
from app.multiplayer.night import follow_rules
from app.rules import commander as commander_rules
from app.rules import coverage
from app.services import Services
from app.stats import recap
from app.stats.repository import DuplicateResult, Participant, ResultError, deck_key_for
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
            # The host computer watches its LAN table as a spectator would. Every hand stays hidden from it, as it would
            # from a host who isn't playing (the all-hands view is for hot-seat games on one computer only).
            return SPECTATOR, None
        raise HTTPException(403, "Join the game first (missing or invalid seat token)")
    return seat, (seat if seat != SPECTATOR else None)


HOST_ONLY_ACTIONS = {"mulligan_finish", "remove_player", "set_table_playmat", "restart_game", "configure",
                     "planar_start", "planar_end"}  # -- planechase -- dealing or putting away the planar deck: a table setting
HOST_ONLY_ACTIONS |= {"add_dummy", "reset_dummy", "set_dummy", "set_bot_level"}  # -- target dummy -- the host seats it, resets it and sets how it blocks


def _planar_pool(services: Services, settings: GameSettings) -> Callable[[], list[PlanarCard]] | None:
    """-- planechase -- the planes and phenomena a new game's planar deck is dealt from (none when the table doesn't planechase).
    A table that wants Planechase without a card database that has planes is refused, rather than started without a deck."""
    if not settings.planechase:
        return None
    try:
        pool = planechase.pool_of(services.cards)
    except CardDatabaseUnavailable:
        pool = []
    if all(c.phenomenon for c in pool):
        raise HTTPException(422, "Planechase needs the planes from the card database: update the card database, or turn Planechase off")
    return lambda: pool


def _check_host_only(room: Room, action: dict[str, Any], *, host: bool) -> None:
    """Some actions are table-level overrides only the host may use (anyone at a hot-seat table)."""
    host_only = action.get("type") in HOST_ONLY_ACTIONS or (action.get("type") == "response_close" and action.get("as_host"))
    if host_only and room.mode == "lan" and not host:
        raise HTTPException(403, "Only the host can do that")


def _check_assets(services: Services, action: dict[str, Any]) -> None:
    """Appearance actions may only reference existing assets of the right kind."""
    wanted: list[tuple[str, str]] = []
    if action.get("type") == "set_appearance":
        if isinstance(action.get("sleeve"), str):
            wanted.append((action["sleeve"], "card_back"))
        if isinstance(action.get("playmat"), dict):
            wanted.append((str(action["playmat"].get("asset_id")), "playmat"))
    elif action.get("type") == "set_table_playmat" and isinstance(action.get("playmat"), dict):
        wanted.append((str(action["playmat"].get("asset_id")), "playmat"))
    for asset_id, kind in wanted:
        try:
            asset = services.assets.get(asset_id)
        except AssetNotFound:
            raise HTTPException(404, "That image isn't in the asset library") from None
        if asset["kind"] != kind:
            raise HTTPException(422, f"That image is a {asset['kind'].replace('_', ' ')}, not a {kind.replace('_', ' ')}")


async def _after_action(services: Services, room: Room, action: dict[str, Any]) -> None:
    """Seat bookkeeping for table-level actions."""
    if action.get("type") == "remove_player":
        pid = str(action.get("player"))
        if pid in room.seats:
            await services.hub.drop_connections(room, pid, code=4403, reason="You left the table")
            room.seats[pid].token = None
            services.hub.persist(room)


def _check_table_open(room: Room, action_type: str | None = None) -> None:
    """-- final board -- after a recorded result the table can be looked at, not changed (``Night.final_board``)."""
    if (why := room.night.final_board(action_type)) is not None:
        raise HTTPException(409, why)


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
    format: TableFormat = "commander"  # "sandbox": free play with Commander decks (app/multiplayer/lobby.py TableFormat)
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
    # Rules automation (docs/AUTOMATION_UX.md): OFF is the sandbox (the safe default).
    automation: AutomationLevel = "off"
    # Lobby turn order: "pod" = d20, then the previous winner goes last (GAME_NIGHT_FLOW.md §2); "seats" = seat 1 first.
    turn_order: TurnOrder = "random"
    card_permissions: CardPermissions = "everyone"  # -- table permissions -- who may change a player's cards (LAN)
    # -- planechase -- a shared planar deck dealt at the start (app/game/handlers/planechase.py); off by default
    planechase: bool = False
    planar_deck_size: int = Field(default=10, ge=2, le=60)
    planar_phenomena: bool = True

    @field_validator("name")
    @classmethod
    def _clean(cls, v: str) -> str:
        return clean_text(v, 80) or "Game"

    @model_validator(mode="after")
    def _sandbox_starts_manual(self) -> CreateGameIn:
        if self.format == "sandbox":
            self.automation = "off"  # a Sandbox table starts as the manual table; the host turns automation on at the table
        return self


ClientActionId = Annotated[str, Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]


class ActionIn(BaseModel):
    action: dict[str, Any]
    as_player: str | None = Field(default=None, alias="as", max_length=16)
    viewer: str | None = Field(default=None, max_length=32)
    # Idempotency: a retried action (same id) is applied once and answered ALREADY_APPLIED.
    client_action_id: ClientActionId | None = None


class MetaIn(BaseModel):
    as_player: str | None = Field(default=None, alias="as", max_length=16)
    viewer: str | None = Field(default=None, max_length=32)


class JoinIn(BaseModel):
    code: str = Field(min_length=4, max_length=12)
    name: str | None = Field(default=None, max_length=40)
    password: str | None = Field(default=None, max_length=100)
    seat: str | None = Field(default=None, max_length=8)
    spectate: bool = False
    handoff: str | None = Field(default=None, max_length=64)  # the deck library this player brought (app/multiplayer/handoff.py)


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
                             mulligan_rule=body.mulligan_rule or "commander_london",
                             mulligan_policy=body.mulligan_policy, priority_helper=body.priority_helper,
                             auto_untap=body.auto_untap, automation=body.automation, turn_order=body.turn_order,
                             card_permissions=body.card_permissions, planechase=body.planechase,
                             planar_deck_size=body.planar_deck_size, planar_phenomena=body.planar_phenomena)
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
    recorded = services.stats.for_game(room.id)
    room.result_id = recorded["id"] if recorded else None
    follow_rules(room)  # -- rules result -- a loaded game the rules already ended asks for its result
    result: dict[str, Any] = {"game": room.summary(), "host_token": room.host_token}
    if mode == "lan" and host_seat:
        viewer, token = services.hub.claim_seat(room, name=None, seat=host_seat if host_seat in room.seats else None)
        room.host_seat = viewer
        result["seat"] = {"player_id": viewer, "token": token}
    services.autosave(room)
    return result


# --------------------------------------------------------------------------- REST


@router.get("/games")
async def list_games(request: Request, services: ServicesDep) -> list[dict[str, Any]]:
    # (-- sync endpoints (wave 30B) -- on the event loop, see game_summary)
    local = is_local_request(request)
    # a practice table (elimination hub) is its owner's alone: never listed. Commanders (for the Play page's tiles) show on the
    # host's own screen only: another device sees no more than the players' names until it sits at the table.
    return [r.summary(commanders=local) for r in services.hub.rooms.values() if (local or r.mode == "lan") and r.practice is None]


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
    settings = GameSettings(starting_life=body.starting_life or STARTING_LIFE.get(body.format, 40), auto_untap=body.auto_untap,
                            deck_privacy=body.deck_privacy, mulligan=policy,
                            # one person runs a hot-seat table: nobody to ask; with rules, the engine asks
                            priority_helper=body.priority_helper if body.mode == "lan" and body.automation == "off" else "off",
                            # test objects: a hot-seat table (one person testing) and a Sandbox table (free play)
                            allow_test_objects=body.mode == "local" or body.format == "sandbox", automation=body.automation,
                            automation_options=AUTOMATION_PRESETS[body.automation].model_copy(), card_permissions=body.card_permissions,
                            planechase=body.planechase, planar_deck_size=body.planar_deck_size, planar_phenomena=body.planar_phenomena)
    state = new_game(setups, name=body.name, format=body.format, settings=settings, shuffle=body.shuffle, first_player=first,
                     related_tokens=services.related_tokens, deck_rows=services.decks.row_overrides,
                     planar_pool=_planar_pool(services, settings))
    if body.automation != "off":
        start_rules(state)
    session = GameSession(state, cards=services.cards, history_limit=services.settings.history_limit, rules=services.rules)
    session.begin_first_turn()  # -- first turn (S7) -- 502.4: no priority in the untap step
    session.notice(f"Game created. {state.players[state.turn.active_player].name} goes first.")
    created = _create_room(services, session, body.mode, body.password, body.host_seat)
    room = services.hub.get(state.id)
    if room is not None:
        room.night.setups = dict(zip(state.seat_order, setups, strict=True))
    return created


@router.get("/games/{game_id}")
async def game_summary(game_id: str, services: ServicesDep) -> dict[str, Any]:
    # -- sync endpoints (wave 30B) -- on the event loop like GET /view (review 29A): actions change the table there with no await in
    # between, so a read on the loop sees whole tables; on the threadpool it iterates the room's connections while a socket joins or leaves
    room = _room(services, game_id)
    return room.summary()


@router.get("/games/{game_id}/view")
async def game_view(  # (review 29A: on the event loop, between actions — a threadpool view read tables half-way through one)
    game_id: str,
    request: Request,
    services: ServicesDep,
    viewer: Annotated[str | None, Query(max_length=32)] = None,
    x_seat_token: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    room = _room(services, game_id)
    v, _ = authorize(room, local=is_local_request(request), token=x_seat_token, viewer=viewer, as_player=None)
    return services.hub.view(room, v)


async def _broadcast_view(services: Services, room: Room, viewer: str) -> dict[str, Any]:
    """Broadcast the change, and reply with ``viewer``'s view of it, built in the broadcast's own pass (-- big boards (views) --)."""
    return await services.hub.broadcast(room, viewer=viewer) or services.hub.view(room, viewer)


@router.post("/games/{game_id}/actions")
async def post_action(
    game_id: str, body: ActionIn, request: Request, services: ServicesDep, x_seat_token: Annotated[str | None, Header()] = None
) -> dict[str, Any]:
    room = _room(services, game_id)
    viewer, actor = authorize(room, local=is_local_request(request), token=x_seat_token, viewer=body.viewer, as_player=body.as_player)
    if actor is None:
        raise HTTPException(403, "Spectators cannot act")
    _check_host_only(room, body.action, host=room.is_host(x_seat_token))
    _check_assets(services, body.action)
    cid = body.client_action_id
    async with room.lock:
        if cid is not None and cid in room.client_actions:
            previous = room.client_actions[cid]
            return {**services.hub.view(room, viewer), "status": "ALREADY_APPLIED", "outcome": previous}
        _check_table_open(room, body.action.get("type"))
        try:
            # -- table permissions -- the host's own seat helps anyone; everyone at a hot-seat table sits at the host computer
            room.session.perform(actor, body.action, host=room.mode == "local" or room.is_host(x_seat_token))
        except ValidationError as exc:
            if cid is not None:
                services.hub.remember_action(room, cid, f"REJECTED: {_validation_message(exc)}")
            raise HTTPException(422, _validation_message(exc)) from exc
        except ActionError as exc:
            if cid is not None:
                services.hub.remember_action(room, cid, f"REJECTED: {exc}")
            raise HTTPException(409, str(exc)) from exc
        if cid is not None:
            services.hub.remember_action(room, cid, "ACCEPTED")
        services.hub.after_change(room)
        await _after_action(services, room, body.action)
    return {**await _broadcast_view(services, room, viewer), "status": "ACCEPTED"}


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
        _check_table_open(room)
        try:
            host = room.mode == "local" or room.is_host(token)  # -- undo policy (gap 3) -- everyone at a hot-seat table is at the host computer
            if op == "undo":  # (-- quick undo request -- an undo of something already seen asks the others first)
                room.session.undo(actor, host=host, others=undo_voters(room, actor))
            else:
                room.session.redo(actor, host=host)
        except ActionError as exc:
            raise HTTPException(409, str(exc)) from exc
        services.hub.after_change(room)
    return await _broadcast_view(services, room, viewer)


class UndoAskIn(MetaIn):
    op: Literal["request", "approve", "decline", "withdraw"]


@router.post("/games/{game_id}/undo-request")
async def undo_request(game_id: str, body: UndoAskIn, request: Request, services: ServicesDep,
                       x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """-- quick undo request -- ask the table to undo the last action, or answer the request waiting for it (approve,
    decline; the requester withdraws). The server undoes it once every other player still in the game approved
    (app/game/undo_requests.py)."""
    room = _room(services, game_id)
    viewer, actor = authorize(room, local=is_local_request(request), token=x_seat_token, viewer=body.viewer, as_player=body.as_player)
    if actor is None:
        raise HTTPException(403, "Spectators can't do that")
    async with room.lock:
        if body.op in ("request", "approve"):
            _check_table_open(room)  # -- final board -- a finished table takes no undo, asked for or approved
        try:
            if body.op == "request":
                host = room.mode == "local" or room.is_host(x_seat_token)
                undo_requests.request(room.session, actor, host=host, others=undo_voters(room, actor))
                undone = None
            else:
                undone = undo_requests.answer(room.session, actor, body.op)
        except ActionError as exc:
            raise HTTPException(409, str(exc)) from exc
        if undone is not None:
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
        summary = services.saves.save(room.session.state, room.session.history, name=name,
                                      extras={"table_snapshots": room.session.table_snapshots})
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
def join_game(body: JoinIn, request: Request, services: ServicesDep,
              x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
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
            if room.night.final_board() is None:  # -- final board -- the finished table keeps the names it ended with
                room.session.perform(viewer, {"type": "rename_player", "name": name})
        except (ActionError, ValidationError) as exc:
            log.info("Could not apply joining player's name: %s", exc)
    # -- bring my decks -- the library sent ahead by the player's own Fyodor, for this seat alone (one use)
    if body.handoff and viewer in room.seats and not room.started:
        library = services.handoffs.take(body.handoff)
        if library is not None:
            services.handoffs.attach(room.id, token, library, services.cards)  # (adds the cards this database lacked)
    # (spectator activities) a spectator of this table taking a lobby seat brings the deck they queued while watching
    if x_seat_token and not room.started and viewer in room.lobby_seats and room.seat_for_token(x_seat_token) == SPECTATOR:
        queued = room.night.queued.pop(x_seat_token, None)
        if queued is not None:
            info = room.lobby_seats[viewer]
            queued.collection = list(info.collection)
            info.deck = info.queued = queued
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
    snaps = services.saves.extras(save_id).get("table_snapshots")
    if isinstance(snaps, list):
        session.table_snapshots = [x for x in snaps if isinstance(x, dict) and isinstance(x.get("state"), dict)][-MAX_SNAPSHOTS:]
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
async def ask_assistant(game_id: str, body: AskIn, request: Request, services: ServicesDep,
                        x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Ask the optional local rules assistant. It sees only the asking player's view."""
    # (-- sync endpoints (wave 30B) -- the view is built on the event loop, between actions, as GET /view's is; the model call blocks: threadpool)
    if services.assistant is None:
        raise HTTPException(404, "The rules assistant is disabled (set FYODOR_ASSISTANT_URL to enable it)")
    room = _room(services, game_id)
    viewer, _ = authorize(room, local=is_local_request(request), token=x_seat_token, viewer=body.viewer, as_player=None)
    if viewer == OMNISCIENT:
        viewer = room.session.state.turn.active_player
    context = build_context(services.hub.view(room, viewer), services.cards)
    try:
        answer = await run_in_threadpool(services.assistant.ask, clean_text(body.question, 1000, multiline=True), context)
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
        # finding tables on the network: searching from this Play page, and the UDP port this computer answers on (or null)
        "discovery": services.settings.discovery,
        "discovery_port": request.app.state.discovery.port,
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

    collection: list[DeckEntry] = Field(default_factory=list, max_length=20000)
    companion_id: str | None = Field(default=None, max_length=64)

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
    format: TableFormat | None = None
    seats: int | None = Field(default=None, ge=1, le=6)
    starting_life: int | None = Field(default=None, ge=1, le=10000)
    deck_privacy: Literal["private", "commander_only", "public"] | None = None
    mulligan_rule: str | None = Field(default=None, max_length=40)
    mulligan_policy: MulliganPolicy | None = None
    priority_helper: Literal["off", "simple"] | None = None
    auto_untap: bool | None = None
    automation: AutomationLevel | None = None
    turn_order: TurnOrder | None = None
    card_permissions: CardPermissions | None = None  # -- table permissions -- (no Ready reset: it's how the table plays, not the deck rules)
    planechase: bool | None = None  # -- planechase -- a shared planar deck (no Ready reset either)
    planar_deck_size: int | None = Field(default=None, ge=2, le=60)
    planar_phenomena: bool | None = None


class ArrangeIn(BaseModel):
    """-- seating -- every lobby seat once, in the order the host wants them seated (seat 1 first)."""

    order: list[Annotated[str, Field(pattern=r"^p[1-6]$")]] = Field(min_length=1, max_length=6)


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
    # Advisory Commander legality checks (never blocking: "play anyway").
    playable = [e for e in entries if e.section != "maybeboard"]
    card_data = services.cards.get_many([e.printing_id for e in playable if e.printing_id])
    warnings = {"commander": [w.model_dump() for w in deck_service.validate(DeckIn(name="deck", entries=playable), services.cards, card_data)][:40]}
    commander_ids = [c.printing_id for c in cards if c.section == "commander" and c.printing_id]
    data = services.cards.get_many(commander_ids) if commander_ids else {}
    levels = {"FULL": 0, "PARTIAL": 0, "REVIEW": 0, "MANUAL": 0}
    for e in playable:
        if e.section == "sideboard":
            continue
        cd = card_data.get(e.printing_id) if e.printing_id else None
        levels[coverage.of_card_data(cd).level if cd else "MANUAL"] += e.quantity
    identity = list(commander_rules.deck_identity(list(data.values())))
    return SubmittedDeck(
        name=clean_text(name, 120) or "Deck",
        cards=cards,
        commanders=[c.name for c in cards if c.section == "commander"],
        color_identity=identity,
        card_count=sum(c.quantity for c in cards if c.section in ("main", "commander", "companion")),
        format=fmt,
        report=report,
        source_kind=kind,
        warnings=warnings,
        coverage=levels,
        commander_ids=commander_ids,
        offline={"name": clean_text(name, 120) or "Deck",
                 "text": format_deck_text([e.model_dump() for e in entries]),
                 "entries": [e.model_dump() for e in entries],
                 "commanders": [c.name for c in cards if c.section == "commander"],
                 "companions": [{"name": cd["name"], "printing_id": cid} for cid, cd in card_data.items()
                                if commander_rules.companion_condition(cd.get("oracle_text")) is not None]},
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
        submitted = _submitted(
            services, entries, name=body.name or deck.name, fmt=deck.format, report=report, kind="library"
        )
        submitted.deck_id = deck.id  # -- saved rows -- its rows are learned into the host's library
        return submitted
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
        raise HTTPException(502 if body.archidekt and not isinstance(exc, sites.DeckLinkRefused) else 422, str(exc)) from exc
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


def _bind_collection(services: Services, deck: SubmittedDeck, body: LobbyDeckIn, fmt: str,
                     existing: list[CollectionCard] | None = None) -> None:
    entries = deck_service.resolve_entries([e for e in body.collection if e.section not in ("tokens", "maybeboard", "stickers")], services.cards)
    data = services.cards.get_many([e.printing_id for e in entries if e.printing_id])
    owned: dict[str, CollectionCard] = {c.oracle_id: c.model_copy(deep=True) for c in existing or []} if "collection" not in body.model_fields_set else {}
    for entry in entries:
        cd = data.get(entry.printing_id or "")
        if cd is None or cd.get("is_token"):
            raise HTTPException(422, "The collection contains unresolved cards; import those decks again")
        if cd.get("type_line") == "Stickers":
            continue  # CR123.2: sheets are not outside-the-game cards.
        oid = cd["oracle_id"]
        if oid in owned:
            owned[oid].quantity += entry.quantity
        else:
            owned[oid] = CollectionCard(printing_id=cd["id"], oracle_id=oid, name=cd["name"], quantity=entry.quantity)
    if body.companion_id:
        requested = services.cards.get(body.companion_id)
        chosen = owned.get(requested["oracle_id"]) if requested else None
        if chosen is None:
            raise HTTPException(422, "Choose a companion from your imported collection")
        cd = services.cards.get(chosen.printing_id)
        if cd is None:
            raise HTTPException(422, "Import that companion again to resolve its card definition")
        starting = [c for c in deck.cards if c.section in ("main", "commander")]
        starting_data = services.cards.get_many([c.printing_id for c in starting if c.printing_id])
        if any(c.printing_id is None for c in starting):
            raise HTTPException(422, "Resolve your starting deck before choosing a companion")
        why = commander_rules.companion_problem(cd, [starting_data[c.printing_id] for c in starting if c.printing_id for _ in range(c.quantity)])
        if why:
            raise HTTPException(422, why)
        if fmt == "commander" and (cd.get("commander_legal") != "legal"
                or not set(cd.get("color_identity") or []) <= set(deck.color_identity)
                or any(c.name == chosen.name for c in starting)):
            raise HTTPException(422, "That companion does not meet Commander color identity, legality, or singleton rules")
        deck.cards = [c for c in deck.cards if c.section != "companion"]
        deck.cards.append(DeckCard("companion", 1, chosen.name, chosen.printing_id))
        deck.card_count = sum(c.quantity for c in deck.cards if c.section in ("main", "commander", "companion"))
    deck.collection = list(owned.values())


class CollectionIn(BaseModel):
    collection: list[DeckEntry] = Field(max_length=20000)


@router.post("/games/{game_id}/lobby/collection")
async def sync_collection(game_id: str, body: CollectionIn, services: ServicesDep,
                          x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    room = _lobby_room(services, game_id)
    viewer, host = _lobby_who(room, x_seat_token)
    resolved = SubmittedDeck(name="Collection", cards=[], commanders=[], color_identity=[], card_count=0)
    await run_in_threadpool(_bind_collection, services, resolved, LobbyDeckIn(collection=body.collection),
                            (room.lobby or LobbySettings()).format)
    async with room.lock:
        if room.started or room.seat_for_token(x_seat_token) != viewer:
            raise HTTPException(409, "Your seat changed while the collection was loading")
        info = room.lobby_seats.setdefault(viewer, LobbySeatInfo())
        if info.collection != resolved.collection:
            info.collection = resolved.collection
            if info.deck is not None:
                info.deck.collection = list(resolved.collection)
            info.ready = False
    await _lobby_changed(services, room)
    return _lobby_response(room, viewer, host)


@router.get("/games/{game_id}/collection")
def own_collection(game_id: str, request: Request, response: Response, services: ServicesDep,
                   x_seat_token: Annotated[str | None, Header()] = None, viewer: str | None = None) -> list[dict[str, Any]]:
    room = _room(services, game_id)
    who, _ = authorize(room, local=is_local_request(request), token=x_seat_token, viewer=viewer, as_player=None)
    # CR 723.4: a controller of this player never inherits access to their outside cards.
    response.headers["Cache-Control"] = "private, no-store"
    return [c.model_dump() for c in room.session.state.collections.get(who, [])]


@router.post("/games/{game_id}/lobby/import")
async def import_personal_deck(game_id: str, body: LobbyDeckIn, request: Request, services: ServicesDep,
                               x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Resolve a personal import without replacing the selected deck or publishing its contents."""
    room = _lobby_room(services, game_id)
    viewer, _ = _lobby_who(room, x_seat_token)
    info = room.lobby_seats.setdefault(viewer, LobbySeatInfo())
    if body.archidekt:
        now = time.monotonic()
        if now - info.last_fetch < ARCHIDEKT_COOLDOWN:
            raise HTTPException(429, "Wait a moment before fetching another deck", headers={"Retry-After": str(ARCHIDEKT_COOLDOWN)})
        info.last_fetch = now
    try:
        deck = await run_in_threadpool(_import_for_lobby, services, body, is_local_request(request))
    except DeckTooLarge as exc:
        raise HTTPException(413, str(exc)) from exc
    if room.started or room.seat_for_token(x_seat_token) != viewer:
        raise HTTPException(409, "Your seat changed while the deck was loading")
    return deck.offline


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
        await run_in_threadpool(_bind_collection, services, deck, body, (room.lobby or LobbySettings()).format, info.collection)
    except DeckTooLarge as exc:
        raise HTTPException(413, str(exc)) from exc
    async with room.lock:
        if room.started or room.seat_for_token(x_seat_token) != viewer:
            raise HTTPException(409, "Your seat changed while the deck was loading")
        info = room.lobby_seats.setdefault(viewer, LobbySeatInfo())
        info.deck = deck
        info.collection = list(deck.collection)
        info.ready = False
    await _lobby_changed(services, room)
    # -- bring my decks -- the art this table lacks for the deck, from the player's own Fyodor over the LAN (in the background)
    if x_seat_token and (library := services.handoffs.brought(room, x_seat_token)) is not None:
        lan_art.bring_art(services, room, library.origin, [c.printing_id for c in deck.cards if c.printing_id])
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


@router.post("/games/{game_id}/lobby/arrange")
async def arrange_seats(
    game_id: str, body: ArrangeIn, services: ServicesDep, x_seat_token: Annotated[str | None, Header()] = None
) -> dict[str, Any]:
    """-- seating -- the host arranges the seats (GAME_NIGHT_FLOW.md §2: "the others keep their relative order, unless the host
    changes it"). The turn-order setting then decides who goes first: the pod rule, a random player, or seat 1."""
    room = _lobby_room(services, game_id)
    _require_host(room, x_seat_token)
    async with room.lock:
        if room.started:
            raise HTTPException(409, "The game has already started")
        try:
            services.hub.arrange_seats(room, body.order)
        except LookupError as exc:
            raise HTTPException(422, str(exc)) from exc
    viewer, host = _lobby_who(room, x_seat_token, seat_required=False)
    await _lobby_changed(services, room)
    return _lobby_response(room, viewer, host)


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
    services.handoffs.drop_seat(room.id, x_seat_token)  # -- bring my decks --
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
    services.handoffs.drop_seat(room.id, room.seats[body.seat].token)  # -- bring my decks --
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
        order = room.claimed_seats()  # -- seating -- as the host arranged them
        if not order:
            raise HTTPException(409, "Nobody has taken a seat")
        if blockers and not body.force:
            raise HTTPException(409, "Not everyone is ready: " + "; ".join(blockers))
        lobby = room.lobby or LobbySettings()
        night = room.night
        pod_rule = lobby.turn_order == "pod" and body.first_player == "random"
        if pod_rule:
            winner = room.last_winner_seat()
            order, night.order_source, night.rolls = night.plan(order, winner)
            night.previous_winner = winner
        else:
            night.order_source, night.rolls, night.previous_winner = "host", [], None
        night.proposal, night.result, night.votes = None, None, {}
        setups = []
        for pid in order:
            info = room.lobby_seats.get(pid) or LobbySeatInfo()
            deck = info.deck
            setups.append(
                PlayerSetup(
                    name=room.seat_name(pid),
                    color=info.color,
                    deck_name=deck.name if deck else None,
                    deck_id=deck.deck_id if deck else None,
                    cards=list(deck.cards) if deck else [],
                    collection=list(info.collection),
                )
            )
        first: int | None = None
        if pod_rule:
            first = 0  # the seats are already in turn order
        elif body.first_player == "random" and lobby.turn_order == "seats":
            first = 0  # -- seating -- the seats as the host arranged them, seat 1 first
        elif body.first_player == "random":
            first = secrets.randbelow(len(setups))
        elif isinstance(body.first_player, int):
            first = body.first_player if 0 <= body.first_player < len(setups) else 0
        night.setups = dict(zip(order, setups, strict=True))
        night.infos = {pid: room.lobby_seats.get(pid) or LobbySeatInfo() for pid in order}
        settings = GameSettings(
            starting_life=lobby.starting_life or STARTING_LIFE.get(lobby.format, 40),
            auto_untap=lobby.auto_untap,
            deck_privacy=lobby.deck_privacy,
            priority_helper=lobby.priority_helper if lobby.automation == "off" else "off",
            mulligan=lobby.policy(),
            automation=lobby.automation,
            automation_options=AUTOMATION_PRESETS[lobby.automation].model_copy(),
            card_permissions=lobby.card_permissions,  # -- table permissions --
            allow_test_objects=lobby.format == "sandbox",  # free play: Spawn a card is on
            planechase=lobby.planechase,  # -- planechase --
            planar_deck_size=lobby.planar_deck_size,
            planar_phenomena=lobby.planar_phenomena,
        )
        state = new_game(
            setups,
            name=lobby.name,
            format=lobby.format,
            settings=settings,
            shuffle=body.shuffle,
            first_player=first,
            related_tokens=services.related_tokens,
            deck_rows=services.decks.row_overrides,  # -- saved rows -- (a deck from the host's library)
            planar_pool=_planar_pool(services, settings),  # -- planechase --
        )
        state.id = room.game_id  # same URL before and after the start
        if lobby.automation != "off":
            start_rules(state)
        session = GameSession(
            state, cards=services.cards, history_limit=services.settings.history_limit, rules=services.rules
        )
        session.begin_first_turn()  # -- first turn (S7) -- 502.4: no priority in the untap step
        session.notice(f"Game started. {state.players[state.turn.active_player].name} goes first.")
        if night.order_source == "winner_last":
            session.notice(f"Turn order: {room.seat_name(night.previous_winner or '')} won the last game and goes last.")
        elif night.order_source == "d20":
            session.notice("Turn order: everyone rolled a d20, highest first.")
        if blockers:
            session.notice("The host started without waiting for everyone.")
        services.hub.start(room, session, order)
        services.handoffs.drop_room(room.id)  # -- bring my decks -- the chosen decks stay; the brought libraries go
        services.autosave(room)
    await services.hub.broadcast(room)
    return {"game": room.summary(), "seats": {pid: pid for pid in room.seats}}


# --------------------------------------------------------------------------- game result


class ResultIn(BaseModel):
    result_type: Literal["single", "multiple", "draw", "no_result"]
    winners: list[str] = Field(default_factory=list, max_length=6)  # seats
    notes: str = Field(default="", max_length=500)
    names: dict[str, str] = Field(default_factory=dict)  # optional seat -> pod player name override

    @field_validator("notes")
    @classmethod
    def _clean_notes(cls, v: str) -> str:
        return clean_text(v, 500, multiline=True)


@router.get("/games/{game_id}/result")
def game_result(game_id: str, services: ServicesDep) -> dict[str, Any] | None:
    room = services.hub.get(game_id)
    return services.stats.for_game(room.night.result_key(room.id) if room else game_id)


@router.post("/games/{game_id}/result", status_code=201)
async def record_result(game_id: str, body: ResultIn, request: Request, services: ServicesDep,
                        x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """End the game: the host records who won. Nothing is ever decided automatically."""
    room = _host_room(services, game_id, request, x_seat_token)
    result = record_game_result(services, room, body.result_type, body.winners, notes=body.notes, names=body.names)
    await services.hub.broadcast(room)
    return result


def record_game_result(services: Services, room: Room, result_type: str, winners: list[str], *, notes: str = "",
                       names: dict[str, str] | None = None, agreed: bool = False, rules: str | None = None) -> dict[str, Any]:
    """Record the current game's result in pod stats and open the post-game vote (GAME_NIGHT_FLOW.md §5-6).

    ``rules``: the rules engine decided it (why), and the players confirmed it (``app.multiplayer.night.follow_rules``)."""
    if room.practice is not None:  # (elimination hub) a practice table is never a pod game
        raise HTTPException(409, "A practice table has no result to record")
    state = room.session.state
    participants = []
    for pid in state.seat_order:
        p = state.players[pid]
        commanders = sorted({c.name for c in state.cards.values() if c.commander_key and c.owner == pid})
        name = clean_text((names or {}).get(pid, ""), 40) or p.name
        participants.append(Participant(seat=pid, name=name, deck_key=deck_key_for(p.deck_id, p.deck_name, commanders),
                                        deck_name=p.deck_name, commanders=commanders))
    if agreed:
        notes = ("Agreed result: every remaining player agreed to end the game. " + notes).strip()
    elif rules:
        notes = (f"Rules result: {rules}. " + notes).strip()
    # -- pod history -- the elimination order and a compact final board, public only (app.stats.recap)
    named = {p.seat: p.name for p in participants}
    eliminations = recap.elimination_order(state, named)
    try:
        result = services.stats.record(
            game_id=room.night.result_key(room.id), result_type=result_type,  # type: ignore[arg-type]
            participants=participants, winners=winners,
            table_name=state.name, format=state.format, started_at=state.created_at, turns=state.turn.number,
            notes=notes, eliminations=eliminations, final_board=recap.final_board(state, named, room.session.cards))
    except DuplicateResult as exc:
        raise HTTPException(409, str(exc)) from exc
    except ResultError as exc:
        raise HTTPException(422, str(exc)) from exc
    room.result_id = result["id"]
    night = room.night
    night.proposal = None
    night.result = {"result_type": result_type, "winners": list(winners), "winner_names": list(result["winners"]),
                    "agreed": agreed, "rules": rules is not None}
    night.votes = {}
    single = result_type == "single" and len(winners) == 1
    night.last_winner_key = (room.seats[winners[0]].token or winners[0]) if single and winners[0] in room.seats else None
    night.history.append({"number": night.number, "result_type": result_type, "winner_names": list(result["winners"]),
                          "agreed": agreed, "rules": rules is not None, "order": [state.players[pid].name for pid in state.seat_order],
                          # -- seating -- how the order was set, and the d20 rounds that set it (by name, like the order)
                          "order_source": night.order_source,
                          "rolls": [{state.players[pid].name: v for pid, v in r.items() if pid in state.players} for r in night.rolls],
                          "turns": state.turn.number, "minutes": max(0, round((time.time() - state.created_at) / 60)),
                          "commanders": {state.players[pid].name: sorted({c.name for c in state.cards.values()
                                                                           if c.commander_key and c.owner == pid})
                                         for pid in state.seat_order},
                          # -- pod history -- who went out, in order; the final board stays in pod stats (``result_id``)
                          "eliminations": recap.elimination_order(state, {}), "result_id": result["id"]})
    services.hub.persist(room)
    services.autobackups.soon("after a recorded game")
    what = {"single": f"{', '.join(result['winners'])} won", "multiple": f"{' and '.join(result['winners'])} won",
            "draw": "a draw", "no_result": "no result (not counted)"}[result_type]
    if agreed:
        room.session.notice(f"Game over by agreement — {what}. This result was agreed by the players, not decided by the rules.")
    elif rules is not None:
        room.session.notice(f"Game over by the rules — {what}. The players confirmed it; result recorded.")
    else:
        room.session.notice(f"Game over — {what}. Result recorded.")
    return result


# --------------------------------------------------------------------------- snapshots + history

MAX_SNAPSHOTS = 30


class SnapshotIn(BaseModel):
    name: str = Field(default="", max_length=80)


def _seated(room: Room, request: Request, token: str | None, viewer: str | None = None) -> tuple[str, str | None]:
    return authorize(room, local=is_local_request(request), token=token, viewer=viewer, as_player=None)


def _snapshot_public(s: dict[str, Any]) -> dict[str, Any]:
    return {k: s[k] for k in ("id", "name", "seq", "turn", "created_at", "by") if k in s}


@router.get("/games/{game_id}/snapshots")
def list_snapshots(game_id: str, request: Request, services: ServicesDep,
                   x_seat_token: Annotated[str | None, Header()] = None) -> list[dict[str, Any]]:
    room = _room(services, game_id)
    _seated(room, request, x_seat_token)
    return [_snapshot_public(s) for s in reversed(room.session.table_snapshots)]


@router.post("/games/{game_id}/snapshots", status_code=201)
async def take_snapshot(game_id: str, body: SnapshotIn, request: Request, services: ServicesDep,
                        x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Save the whole table under a name ("Before board wipe"), to come back to later."""
    room = _room(services, game_id)
    viewer, actor = _seated(room, request, x_seat_token)
    if actor is None:
        raise HTTPException(403, "Spectators can't take snapshots")
    async with room.lock:
        st = room.session.state
        snap = {"id": secrets.token_hex(6), "name": clean_text(body.name, 80) or f"Turn {st.turn.number} · {st.turn.phase}",
                "seq": st.seq, "turn": st.turn.number, "created_at": time.time(), "by": st.players[actor].name,
                "state": st.model_dump(mode="json")}
        room.session.table_snapshots = [*room.session.table_snapshots, snap][-MAX_SNAPSHOTS:]
        room.session.notice(f"{st.players[actor].name} saved a snapshot: “{snap['name']}”.")
    await services.hub.broadcast(room)
    return _snapshot_public(snap)


@router.delete("/games/{game_id}/snapshots/{snapshot_id}", status_code=204)
async def delete_snapshot(game_id: str, snapshot_id: str, request: Request, services: ServicesDep,
                          x_seat_token: Annotated[str | None, Header()] = None) -> Response:
    room = _host_room(services, game_id, request, x_seat_token)
    before = len(room.session.table_snapshots)
    room.session.table_snapshots = [s for s in room.session.table_snapshots if s.get("id") != snapshot_id]
    if len(room.session.table_snapshots) == before:
        raise HTTPException(404, "No such snapshot")
    return Response(status_code=204)


class LoadDeckIn(LobbyDeckIn):
    """A deck to put in your seat mid-game (the table's importer): a pasted list, an Archidekt link, or (on the host
    computer) a saved deck. ``seat``: whose seat, for the host computer at a local table (anyone else loads their own)."""

    seat: str | None = Field(default=None, pattern=r"^p[1-6]$")
    draw: int = Field(default=7, ge=0, le=20)


@router.post("/games/{game_id}/load-deck")
async def load_deck_at_table(game_id: str, body: LoadDeckIn, request: Request, services: ServicesDep,
                             x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Put a new deck in your seat without leaving the table (the scripted tables' importer). Your old cards leave."""
    room = _room(services, game_id)
    viewer, actor = _seated(room, request, x_seat_token)
    local = is_local_request(request)
    seat = body.seat if body.seat and room.mode != "lan" and local else actor
    if seat is None or seat not in room.session.state.players:
        raise HTTPException(403, "Spectators can't load a deck")
    if room.mode == "lan" and seat != actor:
        raise HTTPException(403, "You can only load a deck into your own seat")
    try:
        deck = await run_in_threadpool(_import_for_lobby, services, body, local)
    except DeckTooLarge as exc:
        raise HTTPException(413, str(exc)) from exc
    # a pasted list with no name of its own is called after its commander(s), as the lobby shows it
    name = deck.name if body.name or body.deck_id or deck.name not in ("Deck", "") else " & ".join(deck.commanders) or deck.name
    deck_id = body.deck_id if body.deck_id and local else None
    rows = await run_in_threadpool(services.decks.row_overrides, deck_id) if deck_id else {}  # -- saved rows --
    action = A.LoadDeck(player=seat, deck_name=name[:120], deck_id=deck_id, draw=body.draw, row_overrides=placement.saved_rows(rows),
                        cards=[A.LoadDeckCard(section=c.section, quantity=c.quantity, name=c.name, printing_id=c.printing_id)
                               for c in deck.cards if c.section in ("commander", "companion", "main", "sideboard", "attractions")])
    async with room.lock:
        _check_table_open(room)
        try:
            room.session.perform(seat, action, trusted=True)
        except (ActionError, ValidationError) as exc:
            raise HTTPException(409, str(exc)) from exc
        services.hub.after_change(room)
    await services.hub.broadcast(room)
    return {"deck": deck.name, "cards": deck.card_count, "report": deck.report, "view": services.hub.view(room, viewer)}


async def _restore(services: Services, room: Room, request: Request, token: str | None, state: dict[str, Any],
                   label: str) -> dict[str, Any]:
    viewer, actor = _seated(room, request, token)
    if room.mode == "lan" and not room.is_host(token):
        raise HTTPException(403, "Only the host can restore the table")
    actor = actor or room.session.state.seat_order[0]
    async with room.lock:
        _check_table_open(room)
        try:
            room.session.perform(actor, A.RestoreState(label=label[:120], state=state), trusted=True)
        except (ActionError, ValidationError) as exc:
            raise HTTPException(409, str(exc)) from exc
        services.hub.after_change(room)
    await services.hub.broadcast(room)
    return services.hub.view(room, viewer)


@router.post("/games/{game_id}/snapshots/{snapshot_id}/restore")
async def restore_snapshot(game_id: str, snapshot_id: str, request: Request, services: ServicesDep,
                           x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    room = _room(services, game_id)
    snap = next((s for s in room.session.table_snapshots if s.get("id") == snapshot_id), None)
    if snap is None:
        raise HTTPException(404, "No such snapshot")
    return await _restore(services, room, request, x_seat_token, snap["state"], f"snapshot “{snap['name']}”")


@router.get("/games/{game_id}/history")
async def game_history(game_id: str, request: Request, services: ServicesDep,
                       viewer: Annotated[str | None, Query(max_length=32)] = None,
                       x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Recorded actions with the log lines this viewer may read (for disputes and debugging)."""
    # (-- sync endpoints (wave 30B) -- on the event loop, between actions: a live view and the history's trim, see game_summary)
    room = _room(services, game_id)
    v, _ = _seated(room, request, x_seat_token, viewer)
    history = room.session.history
    log = room.session.view(v)["log"]
    by_seq: dict[int, list[Any]] = {}
    when: dict[int, tuple[Any, Any]] = {}  # (-- undo back to here -- the turn and step each entry happened in, to group them by)
    for entry in log:
        by_seq.setdefault(int(entry["seq"]), []).append(entry["parts"])
        when.setdefault(int(entry["seq"]), (entry.get("turn"), entry.get("phase")))
    players = room.session.state.players
    items = []
    for i, action in enumerate(history.actions, start=1):
        seq = history.base_seq + i
        items.append({"position": i, "seq": seq, "type": action.type,
                      "actor": players[action.actor].name if action.actor in players else None,
                      "log": by_seq.get(seq, []), "undone": i > history.cursor,
                      "turn": when.get(seq, (None, None))[0], "phase": when.get(seq, (None, None))[1]})
    return {"cursor": history.cursor, "base_seq": history.base_seq, "items": items}


@router.get("/games/{game_id}/history/{position}")
async def history_view(game_id: str, position: int, request: Request, services: ServicesDep,
                       viewer: Annotated[str | None, Query(max_length=32)] = None,
                       x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """The table as it was after ``position`` actions, as this viewer could see it then."""
    # (-- sync endpoints (wave 30B) -- on the event loop: it replays the live history, which trimming re-bases in several steps)
    room = _room(services, game_id)
    v, _ = _seated(room, request, x_seat_token, viewer)
    try:
        state = room.session.history.state_at(position)
    except ActionError as exc:
        raise HTTPException(404, str(exc)) from exc
    return build_view(state, v, meta={"historical": True, "position": position})


@router.post("/games/{game_id}/history/{position}/restore")
async def restore_history(game_id: str, position: int, request: Request, services: ServicesDep,
                          x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    room = _room(services, game_id)
    try:
        state = room.session.history.state_at(position)
    except ActionError as exc:
        raise HTTPException(404, str(exc)) from exc
    return await _restore(services, room, request, x_seat_token, state.model_dump(mode="json"),
                          f"back to history step {position} (turn {state.turn.number})")


@router.post("/games/{game_id}/history/{position}/undo")
async def undo_to_history(game_id: str, position: int, body: MetaIn, request: Request, services: ServicesDep,
                          x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """-- undo back to here -- undo every action after ``position`` at once (a whole combat or turn), under the table's undo rules
    (GameSession.undo_to). Unlike Restore from here it is anyone's, it leaves the undone actions to redo, and it adds no history entry."""
    room = _room(services, game_id)
    viewer, actor = authorize(room, local=is_local_request(request), token=x_seat_token, viewer=body.viewer, as_player=body.as_player)
    if actor is None:
        raise HTTPException(403, "Spectators cannot undo")
    async with room.lock:
        _check_table_open(room)
        try:
            host = room.mode == "local" or room.is_host(x_seat_token)
            room.session.undo_to(actor, position, host=host, others=undo_voters(room, actor))
        except ActionError as exc:
            raise HTTPException(409, str(exc)) from exc
        services.hub.after_change(room)
    return await _broadcast_view(services, room, viewer)


@router.post("/games/{game_id}/test/take-back")
async def take_back_test_ending(game_id: str, body: MetaIn, request: Request, services: ServicesDep,
                                x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """-- test-table ending -- "Take it back" at a table with a target dummy: undo back to just before the action that ended the test
    for this seat (it lost, or the rules ended the game), under the table's undo rules (GameSession.undo_to). -- test opponent -- or
    with an opponent the server plays for: its plays go back with the player's action before them."""
    from app.game.autoseat import has_non_human
    from app.game.handlers.dummy import before_the_end

    room = _room(services, game_id)
    viewer, actor = authorize(room, local=is_local_request(request), token=x_seat_token, viewer=body.viewer, as_player=body.as_player)
    if actor is None:
        raise HTTPException(403, "Spectators cannot undo")
    async with room.lock:
        _check_table_open(room)
        session = room.session
        if not has_non_human(session.state):
            raise HTTPException(409, "Take it back is for a test table with a target dummy or a test opponent")
        position = before_the_end(session.state, session.history, actor)
        if position is None:
            raise HTTPException(409, "There is no ending to take back")
        try:
            host = room.mode == "local" or room.is_host(x_seat_token)
            session.undo_to(actor, position, host=host, others=undo_voters(room, actor))
        except ActionError as exc:
            raise HTTPException(409, str(exc)) from exc
        services.hub.after_change(room)
    return await _broadcast_view(services, room, viewer)


# --------------------------------------------------------------------------- host tools


class SeatRef(BaseModel):
    seat: str = Field(pattern=r"^p[1-6]$")


def _host_room(services: Services, game_id: str, request: Request, token: str | None) -> Room:
    room = _room(services, game_id)
    if room.mode == "local":
        require_local(request)
    elif not room.is_host(token):
        raise HTTPException(403, "Only the host can do that")
    return room


@router.post("/games/{game_id}/host/resync")
async def host_resync(game_id: str, request: Request, services: ServicesDep,
                      x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Send every client a fresh authoritative view (they replace, never merge)."""
    room = _host_room(services, game_id, request, x_seat_token)
    await services.hub.broadcast(room, resync=True)
    return {"revision": room.revision, "clients": len(room.connections)}


@router.post("/games/{game_id}/host/reconnect")
async def host_force_reconnect(game_id: str, body: SeatRef, request: Request, services: ServicesDep,
                               x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Drop a seat's connections; their browser reconnects by itself with the same seat."""
    room = _host_room(services, game_id, request, x_seat_token)
    if body.seat not in room.seats:
        raise HTTPException(404, "No such seat")
    dropped = await services.hub.drop_connections(room, body.seat, code=4000, reason="Reconnect requested by the host")
    await services.hub.broadcast(room)
    return {"dropped": dropped}


@router.post("/games/{game_id}/host/seat-link")
async def host_seat_link(game_id: str, body: SeatRef, request: Request, services: ServicesDep,
                         x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Reclaim / assign a seat: issue a fresh seat token (the old one stops working) and a link
    that puts whoever opens it into that seat, with the same hand and permissions."""
    room = _host_room(services, game_id, request, x_seat_token)
    if body.seat not in room.seats:
        raise HTTPException(404, "No such seat")
    if room.started and room.session.state.players.get(body.seat) and room.session.state.players[body.seat].left:
        raise HTTPException(409, "That player has left the table")
    await services.hub.drop_connections(room, body.seat, code=4403, reason="The host gave this seat to someone else")
    token = services.hub.reissue_seat(room, body.seat)
    await services.hub.broadcast(room)
    return {"seat": body.seat, "token": token, "path": f"/#/game/{room.id}?seat_token={token}"}


# --------------------------------------------------------------------------- WebSocket


class WsAction(BaseModel):
    type: Literal["action"]
    action: dict[str, Any]
    as_player: str | None = Field(default=None, alias="as", max_length=16)
    id: int | None = None
    client_action_id: ClientActionId | None = None


class WsSimple(BaseModel):
    type: Literal["undo", "redo", "ping", "view", "resync"]
    as_player: str | None = Field(default=None, alias="as", max_length=16)
    viewer: str | None = Field(default=None, max_length=32)
    id: int | None = None


WS_MESSAGE: TypeAdapter[WsAction | WsSimple] = TypeAdapter(WsAction | WsSimple)


# -- live cursors -- (as in Tabletop Simulator) every seated player's pointer over the 3D table, relayed to the rest of the
# room. Pure presentation: never logged, saved or replayed, and it never touches the game. A position is viewer-independent:
# the nearest seat plus virtual x/y on that seat's battlefield (1000 x 600, the frame of card positions; the wood and the
# rail lie outside it). The client sends only while its pointer is over the 3D table top, never from the hand or the
# panels, so a cursor carries no hidden information. Over a card it also names the card and the point on it (cx/cy, its
# half-widths, -1..1): each screen may lay a board out its own way (the arranged rows), so "over that card" is what
# should match. Only a card everyone can see is named, as for a ping: a hidden card's id would leak.
CURSOR_X = (-400.0, 1400.0)
CURSOR_Y = (-400.0, 1000.0)
MAX_CURSOR_MESSAGE = 256


class WsCursor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["cursor"]
    player: str | None = Field(default=None, max_length=16)
    x: float | None = Field(default=None, allow_inf_nan=False)
    y: float | None = Field(default=None, allow_inf_nan=False)
    card: str | None = Field(default=None, max_length=80)
    cx: float | None = Field(default=None, allow_inf_nan=False)
    cy: float | None = Field(default=None, allow_inf_nan=False)
    gone: bool = False


CURSOR_MESSAGE: TypeAdapter[WsCursor] = TypeAdapter(WsCursor)


def _cursor_message(raw: str) -> WsCursor | None:
    """A cursor message (always small, so it is told apart before the action limiter), else None."""
    if len(raw) > MAX_CURSOR_MESSAGE or '"cursor"' not in raw:
        return None
    try:
        return CURSOR_MESSAGE.validate_json(raw)
    except ValidationError:
        return None


def _cursor_relay(room: Room, conn: Connection, msg: WsCursor) -> dict[str, Any] | None:
    """What the rest of the room sees of a cursor message, or None to drop it (spectators, hot-seat tables, nonsense)."""
    if conn.actor is None or room.mode == "local" or not room.started:
        return None
    if msg.gone:
        return {"type": "cursor", "from": conn.actor, "gone": True}
    if msg.player not in room.session.state.players or msg.x is None or msg.y is None:
        return None
    x = round(min(CURSOR_X[1], max(CURSOR_X[0], msg.x)), 1)
    y = round(min(CURSOR_Y[1], max(CURSOR_Y[0], msg.y)), 1)
    out: dict[str, Any] = {"type": "cursor", "from": conn.actor, "player": msg.player, "x": x, "y": y}
    state = room.session.state
    card = state.cards.get(msg.card) if msg.card is not None else None
    if card is not None and msg.cx is not None and msg.cy is not None and publicly_visible(state, card):
        out.update(card=card.id, cx=round(min(1.0, max(-1.0, msg.cx)), 3), cy=round(min(1.0, max(-1.0, msg.cy)), 3))
    return out


async def _to_others(room: Room, conn: Connection, message: dict[str, Any]) -> None:
    for other in list(room.connections.values()):
        if other.id == conn.id:
            continue
        try:
            await other.send(message)
        except Exception:  # noqa: BLE001,S112 - best effort: that socket's own loop notices it closed
            continue


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

    async def close(code: int, reason: str) -> None:
        await websocket.close(code=code, reason=reason)

    conn = Connection(viewer=viewer, send=send, actor=actor, host=room.is_host(params.get("token")), close=close)
    services.hub.connect(room, conn)
    limiter = _RateLimiter()
    cursor_limiter = _RateLimiter(rate=20.0, burst=20.0)  # -- live cursors -- the client sends at most ~15 a second
    cursor_shown = False
    try:
        await send(services.hub.message(room, viewer, host=conn.host))
        await services.hub.broadcast(room)  # others see the connection indicator
        while True:
            raw = await websocket.receive_text()
            if len(raw) > MAX_WS_MESSAGE:
                await send({"type": "error", "message": "Message too large"})
                continue
            if (cursor := _cursor_message(raw)) is not None:
                # -- live cursors -- their own budget, so moving the mouse never slows actions down; excess is dropped quietly
                relay = _cursor_relay(room, conn, cursor) if cursor_limiter.allow() else None
                if relay is not None:
                    cursor_shown = not cursor.gone
                    await _to_others(room, conn, relay)
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
            if cursor_shown and conn.actor is not None:  # -- live cursors -- they left the table: their pointer goes too
                await _to_others(room, conn, {"type": "cursor", "from": conn.actor, "gone": True})
            await services.hub.broadcast(room)  # "Reconnecting…"
            seat = room.seats.get(conn.viewer)
            if seat is not None and seat.connections == 0:
                _later(_presence_expired(services, room, conn.viewer))


_background: set[asyncio.Task[None]] = set()


def _later(coro: Any) -> None:
    task = asyncio.get_running_loop().create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


async def _presence_expired(services: Services, room: Room, pid: str) -> None:
    """After the grace period a player who hasn't come back shows as Disconnected."""
    await asyncio.sleep(RECONNECT_GRACE + 0.5)
    seat = room.seats.get(pid)
    if services.hub.get(room.id) is room and seat is not None and seat.presence() == "disconnected":
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
    if msg.type == "resync":  # the client noticed a gap: the server's state wins
        await send({**services.hub.message(room, conn.viewer, host=conn.host), "resync": True, "id": msg.id})
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
            _check_assets(services, msg.action)
        except HTTPException as exc:
            await send({"type": "error", "id": msg.id, "message": str(exc.detail)})
            return
    cid = msg.client_action_id if isinstance(msg, WsAction) else None
    async with room.lock:
        if cid is not None and cid in room.client_actions:
            previous = room.client_actions[cid]
            if previous.startswith("REJECTED"):
                await send({"type": "error", "id": msg.id, "status": "REJECTED", "message": previous.removeprefix("REJECTED: ")})
            else:
                await send({"type": "ack", "id": msg.id, "status": "ALREADY_APPLIED"})
            return
        if (closed := room.night.final_board(msg.action.get("type") if isinstance(msg, WsAction) else None)) is not None:
            await send({"type": "error", "id": msg.id, "status": "REJECTED", "message": closed})
            return
        try:
            if isinstance(msg, WsAction):
                room.session.perform(actor, msg.action, host=room.mode == "local" or conn.host)  # -- table permissions --
            elif msg.type == "undo":  # -- undo policy (gap 3) -- (-- quick undo request -- ``others``: see _history_op)
                room.session.undo(actor, host=room.mode == "local" or conn.host, others=undo_voters(room, actor))
            else:
                room.session.redo(actor, host=room.mode == "local" or conn.host)
        except ValidationError as exc:
            if cid is not None:
                services.hub.remember_action(room, cid, f"REJECTED: {_validation_message(exc)}")
            await send({"type": "error", "id": msg.id, "status": "REJECTED", "message": _validation_message(exc)})
            return
        except ActionError as exc:
            if cid is not None:
                services.hub.remember_action(room, cid, f"REJECTED: {exc}")
            await send({"type": "error", "id": msg.id, "status": "REJECTED", "message": str(exc)})
            return
        if cid is not None:
            services.hub.remember_action(room, cid, "ACCEPTED")
        services.hub.after_change(room)
    if isinstance(msg, WsAction):
        await _after_action(services, room, msg.action)
    await send({"type": "ack", "id": msg.id, "status": "ACCEPTED"})
    await services.hub.broadcast(room)
