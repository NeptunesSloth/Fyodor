"""Game rooms, seats and live connections (host-authoritative).

* **local** rooms are hot-seat tables. Any *loopback* client may view or act as any seat
  (and use the omniscient "open table" view). They are never reachable from the LAN.
* **lan** rooms require a seat token. A token is issued when a seat is claimed (with the
  room code and optional password) and is used to reconnect. Every connection receives a
  view built for its own seat; spectators get the public view.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from app.game.factory import PLAYER_COLORS
from app.game.session import GameSession
from app.game.visibility import OMNISCIENT, SPECTATOR
from app.multiplayer.lobby import LobbySeatInfo, LobbySettings, deck_summary

log = logging.getLogger(__name__)

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
Mode = Literal["local", "lan"]
Phase = Literal["lobby", "playing"]
SendFn = Callable[[dict[str, Any]], Awaitable[None]]


def _hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)


@dataclass
class Seat:
    player_id: str
    token: str | None = None
    claimed_name: str | None = None
    connections: int = 0


@dataclass
class Connection:
    viewer: str  # player id, SPECTATOR or OMNISCIENT
    send: SendFn
    actor: str | None  # who actions are attributed to (None for spectators)
    host: bool = False  # connected with host rights (lobby management)
    id: str = field(default_factory=lambda: secrets.token_hex(4))


class GameNotStarted(RuntimeError):
    pass


@dataclass
class Room:
    mode: Mode
    code: str
    host_token: str
    game_id: str
    game: GameSession | None = None
    phase: Phase = "playing"
    lobby: LobbySettings | None = None
    lobby_seats: dict[str, LobbySeatInfo] = field(default_factory=dict)
    host_seat: str | None = None
    password_salt: bytes | None = None
    password_hash: bytes | None = None
    seats: dict[str, Seat] = field(default_factory=dict)
    spectator_tokens: set[str] = field(default_factory=set)
    connections: dict[str, Connection] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    actions_since_save: int = 0
    created_at: float = field(default_factory=time.time)

    @property
    def id(self) -> str:
        return self.game_id

    @property
    def started(self) -> bool:
        return self.game is not None

    @property
    def session(self) -> GameSession:
        if self.game is None:
            raise GameNotStarted("The game hasn't started yet")
        return self.game

    def check_password(self, password: str | None) -> bool:
        if self.password_hash is None or self.password_salt is None:
            return True
        return hmac.compare_digest(_hash_password(password or "", self.password_salt), self.password_hash)

    def seat_for_token(self, token: str | None) -> str | None:
        """Player id for a seat token, SPECTATOR for a spectator token, else None."""
        if not token:
            return None
        for seat in self.seats.values():
            if seat.token and hmac.compare_digest(seat.token, token):
                return seat.player_id
        if any(hmac.compare_digest(t, token) for t in self.spectator_tokens):
            return SPECTATOR
        return None

    def is_host(self, token: str | None) -> bool:
        """The host token, or the seat token of the host's own seat."""
        if not token:
            return False
        if hmac.compare_digest(self.host_token, token):
            return True
        return self.host_seat is not None and self.seat_for_token(token) == self.host_seat

    def seat_name(self, pid: str) -> str:
        if self.game is not None and pid in self.game.state.players:
            return self.game.state.players[pid].name
        info = self.lobby_seats.get(pid)
        seat = self.seats.get(pid)
        return (
            (info.name if info and info.name else None)
            or (seat.claimed_name if seat else None)
            or f"Seat {pid[1:]}"
        )

    def summary(self) -> dict[str, Any]:
        common = {
            "id": self.game_id,
            "mode": self.mode,
            "phase": self.phase,
            "code": self.code if self.mode == "lan" else None,
            "has_password": self.password_hash is not None,
            "spectators": sum(1 for c in self.connections.values() if c.viewer == SPECTATOR),
        }
        if self.game is None:
            lobby = self.lobby or LobbySettings()
            return {
                **common,
                "name": lobby.name,
                "format": lobby.format,
                "turn": 0,
                "players": [
                    {
                        "id": pid,
                        "name": self.seat_name(pid),
                        "claimed": s.token is not None,
                        "connected": s.connections > 0,
                    }
                    for pid, s in self.seats.items()
                ],
                "updated_at": self.created_at,
            }
        st = self.game.state
        return {
            **common,
            "name": st.name,
            "format": st.format,
            "turn": st.turn.number,
            "players": [
                {
                    "id": pid,
                    "name": st.players[pid].name,
                    "claimed": self.seats[pid].token is not None,
                    "connected": self.seats[pid].connections > 0,
                }
                for pid in st.seat_order
            ],
            "updated_at": self.game.updated_at,
        }

    # -- lobby -----------------------------------------------------------------------
    def lobby_view(self, viewer: str, *, host: bool = False) -> dict[str, Any]:
        """The pregame lobby as one viewer may see it (deck lists follow the privacy setting)."""
        settings = self.lobby or LobbySettings()
        seats = []
        for pid, seat in self.seats.items():
            info = self.lobby_seats.setdefault(pid, LobbySeatInfo())
            seats.append(
                {
                    "id": pid,
                    "name": self.seat_name(pid),
                    "color": info.color or PLAYER_COLORS[(int(pid[1:]) - 1) % len(PLAYER_COLORS)],
                    "claimed": seat.token is not None,
                    "connected": seat.connections > 0,
                    "ready": info.ready,
                    "host": pid == self.host_seat,
                    "deck": deck_summary(info.deck, privacy=settings.deck_privacy, own=pid == viewer),
                }
            )
        return {
            "game": {
                "id": self.game_id,
                "mode": self.mode,
                "code": self.code if self.mode == "lan" else None,
                "has_password": self.password_hash is not None,
            },
            "phase": self.phase,
            "viewer": viewer,
            "is_host": host,
            "settings": settings.model_dump(),
            "seats": seats,
            "spectators": sum(1 for c in self.connections.values() if c.viewer == SPECTATOR),
            "start_blockers": self.start_blockers(),
        }

    def start_blockers(self) -> list[str]:
        """Why the host can't start yet without overriding (empty when everyone is ready)."""
        claimed = [pid for pid, s in self.seats.items() if s.token is not None]
        if not claimed:
            return ["Nobody has taken a seat"]
        out = []
        for pid in claimed:
            info = self.lobby_seats.get(pid) or LobbySeatInfo()
            if info.deck is None:
                out.append(f"{self.seat_name(pid)} hasn't chosen a deck")
            elif not info.ready:
                out.append(f"{self.seat_name(pid)} isn't ready")
        return out


class GameHub:
    def __init__(self, *, autosave: Callable[[Room], None] | None = None, autosave_every: int = 10) -> None:
        self.rooms: dict[str, Room] = {}
        self.join_failures: dict[str, list[float]] = {}  # client ip -> recent failed join times
        self._autosave = autosave
        self.autosave_every = max(1, autosave_every)

    # -- rooms -----------------------------------------------------------------------
    def create_room(self, session: GameSession, *, mode: Mode = "local", password: str | None = None) -> Room:
        room = self._new_room(session.state.id, mode, password)
        room.game = session
        for pid in session.state.seat_order:
            room.seats[pid] = Seat(player_id=pid)
        self.rooms[room.id] = room
        log.info("Created %s room %s (%s)", mode, room.id, session.state.name)
        return room

    def create_lobby(self, settings: LobbySettings, *, password: str | None = None) -> Room:
        """A LAN room whose players pick their own decks before the host starts the game."""
        room = self._new_room(secrets.token_hex(8), "lan", password)
        room.phase = "lobby"
        room.lobby = settings
        self.resize_lobby(room, settings.seats)
        self.rooms[room.id] = room
        log.info("Created lobby %s (%s)", room.id, settings.name)
        return room

    def _new_room(self, game_id: str, mode: Mode, password: str | None) -> Room:
        room = Room(mode=mode, code=self._new_code(), host_token=secrets.token_urlsafe(24), game_id=game_id)
        if password:
            room.password_salt = secrets.token_bytes(16)
            room.password_hash = _hash_password(password, room.password_salt)
        return room

    def _new_code(self) -> str:
        while True:
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
            if all(r.code != code for r in self.rooms.values()):
                return code

    def get(self, game_id: str) -> Room | None:
        return self.rooms.get(game_id)

    def by_code(self, code: str) -> Room | None:
        code = code.strip().upper()
        return next((r for r in self.rooms.values() if r.mode == "lan" and hmac.compare_digest(r.code, code)), None)

    def close(self, game_id: str) -> None:
        room = self.rooms.pop(game_id, None)
        if room:
            log.info("Closed room %s", game_id)

    # -- lobby -----------------------------------------------------------------------
    def resize_lobby(self, room: Room, count: int) -> None:
        """Add or remove empty seats (a seat someone has taken is never removed)."""
        pids = [f"p{i + 1}" for i in range(count)]
        for pid in list(room.seats):
            if pid not in pids and room.seats[pid].token is not None:
                raise PermissionError(f"{room.seat_name(pid)} is sitting in seat {pid[1:]}; kick them first")
        for pid in list(room.seats):
            if pid not in pids:
                del room.seats[pid]
                room.lobby_seats.pop(pid, None)
        for pid in pids:
            room.seats.setdefault(pid, Seat(player_id=pid))
            room.lobby_seats.setdefault(pid, LobbySeatInfo())

    def release_seat(self, room: Room, pid: str) -> None:
        """Free a lobby seat (leaving or being kicked): its token stops working at once."""
        seat = room.seats[pid]
        seat.token = None
        seat.claimed_name = None
        room.lobby_seats[pid] = LobbySeatInfo()

    def move_seat(self, room: Room, pid: str, target: str) -> None:
        if target not in room.seats:
            raise LookupError("No such seat")
        if room.seats[target].token is not None:
            raise PermissionError("That seat is already taken")
        src, dst = room.seats[pid], room.seats[target]
        dst.token, dst.claimed_name, dst.connections = src.token, src.claimed_name, src.connections
        src.token, src.claimed_name, src.connections = None, None, 0
        room.lobby_seats[target], room.lobby_seats[pid] = room.lobby_seats[pid], LobbySeatInfo()
        if room.host_seat == pid:
            room.host_seat = target
        for conn in room.connections.values():
            if conn.viewer == pid:
                conn.viewer = conn.actor = target

    def start(self, room: Room, session: GameSession, order: list[str]) -> None:
        """Seat the players in ``order`` (lobby seat ids) as p1..pN of the new game."""
        mapping = {old: f"p{i + 1}" for i, old in enumerate(order)}
        seats: dict[str, Seat] = {}
        for old, new in mapping.items():
            seat = room.seats[old]
            seats[new] = Seat(
                player_id=new, token=seat.token, claimed_name=seat.claimed_name, connections=seat.connections
            )
        for pid in session.state.seat_order:
            seats.setdefault(pid, Seat(player_id=pid))
        for conn in room.connections.values():
            if conn.viewer in room.seats:
                new_pid = mapping.get(conn.viewer)
                conn.viewer = new_pid or SPECTATOR
                conn.actor = new_pid
        room.seats = seats
        room.host_seat = mapping.get(room.host_seat or "")
        room.game = session
        room.phase = "playing"
        room.lobby_seats = {}

    # -- seats -----------------------------------------------------------------------
    def claim_seat(self, room: Room, *, name: str | None, seat: str | None, spectate: bool = False) -> tuple[str, str]:
        """Claim a free seat (or become a spectator). Returns (viewer, token)."""
        token = secrets.token_urlsafe(24)
        if spectate:
            room.spectator_tokens.add(token)
            return SPECTATOR, token
        free = [s for s in room.seats.values() if s.token is None]
        if seat is not None:
            chosen = room.seats.get(seat)
            if chosen is None:
                raise LookupError("No such seat")
            if chosen.token is not None:
                raise PermissionError("That seat is already taken")
        elif free:
            chosen = free[0]
        else:
            raise PermissionError("The table is full — join as a spectator")
        chosen.token = token
        chosen.claimed_name = name
        if not room.started:
            room.lobby_seats[chosen.player_id] = LobbySeatInfo(name=name or "")
        return chosen.player_id, token

    # -- live connections ------------------------------------------------------------
    def connect(self, room: Room, conn: Connection) -> None:
        room.connections[conn.id] = conn
        if conn.viewer in room.seats:
            room.seats[conn.viewer].connections += 1

    def disconnect(self, room: Room, conn: Connection) -> None:
        if room.connections.pop(conn.id, None) is not None and conn.viewer in room.seats:
            room.seats[conn.viewer].connections = max(0, room.seats[conn.viewer].connections - 1)

    async def broadcast(self, room: Room) -> None:
        """Send each connection a fresh view built for its own viewer."""
        cache: dict[str, dict[str, Any]] = {}
        stale: list[Connection] = []
        for conn in list(room.connections.values()):
            key = f"{conn.viewer}:{conn.host}"
            message = cache.get(key)
            if message is None:
                message = cache[key] = self.message(room, conn.viewer, host=conn.host)
            try:
                await conn.send(message)
            except Exception as exc:  # noqa: BLE001 - a dead socket must not break the table for others
                log.info("Dropping connection %s: %s", conn.id, exc)
                stale.append(conn)
        for conn in stale:
            self.disconnect(room, conn)

    async def send_to(self, room: Room, viewer: str, message: dict[str, Any]) -> None:
        for conn in [c for c in room.connections.values() if c.viewer == viewer]:
            try:
                await conn.send(message)
            except Exception:  # noqa: BLE001 - best effort
                self.disconnect(room, conn)

    def message(self, room: Room, viewer: str, *, host: bool = False) -> dict[str, Any]:
        if not room.started:
            return {"type": "lobby", "lobby": room.lobby_view(viewer, host=host)}
        return {"type": "state", "view": self.view(room, viewer)}

    def view(self, room: Room, viewer: str) -> dict[str, Any]:
        meta = {
            "mode": room.mode,
            "code": room.code if room.mode == "lan" else None,
            "seats": {pid: {"claimed": s.token is not None, "connected": s.connections > 0} for pid, s in room.seats.items()},
        }
        return room.session.view(viewer, meta=meta)

    def after_change(self, room: Room) -> None:
        room.actions_since_save += 1
        if self._autosave and room.actions_since_save >= self.autosave_every:
            room.actions_since_save = 0
            try:
                self._autosave(room)
            except Exception:  # noqa: BLE001 - autosave failure must not break play; it is logged loudly
                log.exception("Autosave failed for game %s", room.id)


def valid_viewer(room: Room, viewer: str) -> bool:
    return viewer in room.seats or viewer in (SPECTATOR, OMNISCIENT)
