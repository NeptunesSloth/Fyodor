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

from app.game.session import GameSession
from app.game.visibility import OMNISCIENT, SPECTATOR

log = logging.getLogger(__name__)

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
Mode = Literal["local", "lan"]
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
    id: str = field(default_factory=lambda: secrets.token_hex(4))


@dataclass
class Room:
    session: GameSession
    mode: Mode
    code: str
    host_token: str
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
        return self.session.state.id

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
        return bool(token) and hmac.compare_digest(self.host_token, token or "")

    def summary(self) -> dict[str, Any]:
        st = self.session.state
        return {
            "id": st.id,
            "name": st.name,
            "format": st.format,
            "mode": self.mode,
            "code": self.code if self.mode == "lan" else None,
            "has_password": self.password_hash is not None,
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
            "spectators": sum(1 for c in self.connections.values() if c.viewer == SPECTATOR),
            "updated_at": self.session.updated_at,
        }


class GameHub:
    def __init__(self, *, autosave: Callable[[Room], None] | None = None, autosave_every: int = 10) -> None:
        self.rooms: dict[str, Room] = {}
        self.join_failures: dict[str, list[float]] = {}  # client ip -> recent failed join times
        self._autosave = autosave
        self.autosave_every = max(1, autosave_every)

    # -- rooms -----------------------------------------------------------------------
    def create_room(self, session: GameSession, *, mode: Mode = "local", password: str | None = None) -> Room:
        code = self._new_code()
        room = Room(session=session, mode=mode, code=code, host_token=secrets.token_urlsafe(24))
        if password:
            room.password_salt = secrets.token_bytes(16)
            room.password_hash = _hash_password(password, room.password_salt)
        for pid in session.state.seat_order:
            room.seats[pid] = Seat(player_id=pid)
        self.rooms[room.id] = room
        log.info("Created %s room %s (%s)", mode, room.id, session.state.name)
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
            view = cache.get(conn.viewer)
            if view is None:
                view = cache[conn.viewer] = self.view(room, conn.viewer)
            try:
                await conn.send({"type": "state", "view": view})
            except Exception as exc:  # noqa: BLE001 - a dead socket must not break the table for others
                log.info("Dropping connection %s: %s", conn.id, exc)
                stale.append(conn)
        for conn in stale:
            self.disconnect(room, conn)

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
