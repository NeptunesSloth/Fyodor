"""Game rooms over REST and WebSocket."""

from __future__ import annotations

import ipaddress
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
from pydantic import BaseModel, Field, TypeAdapter, ValidationError, field_validator

from app.api.deps import get_services
from app.decks.repository import DeckNotFound
from app.game.errors import ActionError
from app.game.factory import DeckCard, PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameSettings
from app.game.visibility import OMNISCIENT, SPECTATOR
from app.multiplayer.hub import Connection, Room
from app.services import Services
from app.storage.save_format import SaveFormatError
from app.storage.saves import SaveNotFound
from app.textutil import clean_text

log = logging.getLogger(__name__)
router = APIRouter(tags=["games"])
ServicesDep = Annotated[Services, Depends(get_services)]
MAX_WS_MESSAGE = 64 * 1024

# --------------------------------------------------------------------------- access control


def _peer_is_loopback(host: str | None, forwarded_for: str | None) -> bool:
    if host == "testclient":  # starlette TestClient
        host = "127.0.0.1"
    try:
        loopback = host is not None and ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host == "localhost"
    if loopback and forwarded_for:
        # Requests relayed by the local dev proxy carry the real client address.
        first = forwarded_for.split(",")[0].strip()
        try:
            return ipaddress.ip_address(first).is_loopback
        except ValueError:
            return False
    return loopback


def is_local_request(request: Request | WebSocket) -> bool:
    client = request.client
    return _peer_is_loopback(client.host if client else None, request.headers.get("x-forwarded-for"))


def require_local(request: Request) -> None:
    if not is_local_request(request):
        raise HTTPException(403, "Only available on the host computer")


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
    players: list[PlayerIn] = Field(min_length=1, max_length=6)
    shuffle: bool = True
    first_player: int | Literal["random"] | None = None
    starting_life: int | None = Field(default=None, ge=1, le=10000)
    auto_untap: bool = True
    host_seat: str | None = Field(default="p1", max_length=8)

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
        names = services.cards.get_many([e.printing_id for e in deck.entries if e.printing_id])
        cards = [
            DeckCard(e.section, e.quantity, names[e.printing_id]["name"] if e.printing_id in names else e.name,
                     e.printing_id if e.printing_id in names else None)
            for e in deck.entries
        ]
        setups.append(PlayerSetup(name=p.name, deck_id=deck.id, deck_name=deck.name, cards=cards, color=p.color))
    return setups


def _create_room(services: Services, session: GameSession, mode: str, password: str | None,
                 host_seat: str | None) -> dict[str, Any]:
    room = services.hub.create_room(session, mode=mode, password=password)  # type: ignore[arg-type]
    result: dict[str, Any] = {"game": room.summary(), "host_token": room.host_token}
    if mode == "lan" and host_seat:
        viewer, token = services.hub.claim_seat(room, name=None, seat=host_seat if host_seat in room.seats else None)
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
    setups = _setup_players(services, body)
    first = None
    if body.first_player == "random":
        import secrets

        first = secrets.randbelow(len(setups))
    elif isinstance(body.first_player, int):
        first = body.first_player
    settings = GameSettings(starting_life=body.starting_life or {"commander": 40}.get(body.format, 20), auto_untap=body.auto_untap)
    state = new_game(setups, name=body.name, format=body.format, settings=settings, shuffle=body.shuffle, first_player=first)
    session = GameSession(state, cards=services.cards, history_limit=services.settings.history_limit)
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
    if name and viewer in room.seats:
        room.session.notice(f"{name} took the seat of {room.session.state.players[viewer].name}.")
    return {"game_id": room.id, "viewer": viewer, "token": token, "game": room.summary()}


@router.get("/saves")
def list_saves(request: Request, services: ServicesDep) -> list[dict[str, Any]]:
    require_local(request)
    return services.saves.list()


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
    session = GameSession(state, cards=services.cards, history=history, history_limit=services.settings.history_limit)
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
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(p) for p in first.get("loc", ()))
    return f"Invalid action: {first.get('msg', 'bad input')}" + (f" ({loc})" if loc else "")


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

    conn = Connection(viewer=viewer, send=send, actor=actor)
    services.hub.connect(room, conn)
    limiter = _RateLimiter()
    try:
        await send({"type": "state", "view": services.hub.view(room, viewer)})
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
