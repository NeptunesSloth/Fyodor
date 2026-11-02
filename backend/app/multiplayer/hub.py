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

from app.game import undo_requests, undo_rights
from app.game.factory import PLAYER_COLORS
from app.game.session import GameSession
from app.game.visibility import OMNISCIENT, SPECTATOR
from app.multiplayer.elimination import PracticeLink, Pulse
from app.multiplayer.lobby import LobbySeatInfo, LobbySettings, deck_summary
from app.multiplayer.night import Night, follow_rules
from app.storage.journal import RoomJournal

log = logging.getLogger(__name__)

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
Mode = Literal["local", "lan"]
Phase = Literal["lobby", "playing"]
SendFn = Callable[[dict[str, Any]], Awaitable[None]]


def _hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)


RECONNECT_GRACE = 60.0  # seconds a dropped player shows as "Reconnecting…" before "Disconnected"
Presence = Literal["open", "connected", "reconnecting", "disconnected"]


@dataclass
class Seat:
    player_id: str
    token: str | None = None
    claimed_name: str | None = None
    connections: int = 0
    last_seen: float | None = None  # when the last connection of this seat dropped

    def presence(self, now: float | None = None) -> Presence:
        if self.token is None:
            return "open"
        if self.connections > 0:
            return "connected"
        if self.last_seen is not None and (now or time.time()) - self.last_seen < RECONNECT_GRACE:
            return "reconnecting"
        return "disconnected"

    def public(self) -> dict[str, Any]:
        return {"claimed": self.token is not None, "connected": self.connections > 0, "presence": self.presence()}


@dataclass
class Connection:
    viewer: str  # player id, SPECTATOR or OMNISCIENT
    send: SendFn
    actor: str | None  # who actions are attributed to (None for spectators)
    host: bool = False  # connected with host rights (lobby management)
    close: Callable[[int, str], Awaitable[None]] | None = None  # drop this socket (the client reconnects)
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
    revision: int = 0  # bumped on every authoritative update sent to clients
    result_id: str | None = None  # the recorded pod result for this game, if any
    # client_action_id -> outcome ("ACCEPTED" / "REJECTED: …"): a retried action applies once.
    client_actions: dict[str, str] = field(default_factory=dict)
    night: Night = field(default_factory=Night)  # game night: turn order, agreed endings, rematch vote
    pulse: Pulse = field(default_factory=Pulse)  # major public events of the current game (elimination hub)
    practice: PracticeLink | None = None  # a private practice table (elimination hub): whose it is

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
                    "presence": seat.presence(),
                    "ready": info.ready,
                    "host": pid == self.host_seat,
                    "deck": deck_summary(info.deck, privacy=settings.deck_privacy, own=pid == viewer, table_format=settings.format),
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
            # Lobby updates reach a browser both as HTTP responses and WebSocket pushes, in any
            # order; the revision lets it drop an older one that arrives late.
            "revision": self.revision,
            "viewer": viewer,
            "is_host": host,
            "settings": settings.model_dump(),
            "mulligan": (lambda p: p.model_dump() if p else None)(settings.policy()),
            "seats": seats,
            "spectators": sum(1 for c in self.connections.values() if c.viewer == SPECTATOR),
            "start_blockers": self.start_blockers(),
            # tonight's finished games (public: names, winners, turns), for the session recap
            "night": [dict(h) for h in self.night.history],
        }

    def start_blockers(self) -> list[str]:
        """Why the host can't start yet without overriding (empty when everyone is ready)."""
        claimed = [pid for pid, s in self.seats.items() if s.token is not None]
        if not claimed:
            return ["Nobody has taken a seat"]
        out = []
        policy = (self.lobby or LobbySettings()).policy()
        if policy is not None and policy.needs_definition:
            out.append(f"The {policy.display_name} mulligan isn't defined yet (Table settings)")
        for pid in claimed:
            info = self.lobby_seats.get(pid) or LobbySeatInfo()
            if info.deck is None:
                out.append(f"{self.seat_name(pid)} hasn't chosen a deck")
            elif not info.ready:
                out.append(f"{self.seat_name(pid)} isn't ready")
        return out


class GameHub:
    def __init__(self, *, autosave: Callable[[Room], None] | None = None, autosave_every: int = 10,
                 asset_info: Callable[[set[str]], dict[str, Any]] | None = None, journal: RoomJournal | None = None) -> None:
        self.rooms: dict[str, Room] = {}
        self.journal = journal
        self.asset_info = asset_info  # asset id -> {url, width, height} for sleeves / playmats in views
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
        self.track(room)
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

    def create_practice(self, session: GameSession, link: PracticeLink) -> Room:
        """A private practice table (ELIMINATION_HUB.md): one seat, no host, never listed, joined by code, journaled or saved."""
        room = self._new_room(session.state.id, "lan", None)
        room.game, room.practice = session, link
        room.seats = {pid: Seat(player_id=pid) for pid in session.state.seat_order}
        self.rooms[room.id] = room
        log.info("Created practice table %s for %s at %s", room.id, link.seat, link.live)
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
        return next((r for r in self.rooms.values() if r.mode == "lan" and r.practice is None and hmac.compare_digest(r.code, code)), None)

    def close(self, game_id: str) -> None:
        room = self.rooms.pop(game_id, None)
        if room:
            if room.game is not None:
                room.game.history.listener = None
            log.info("Closed room %s", game_id)
        if self.journal is not None:
            self.journal.forget(game_id)

    # -- crash recovery --------------------------------------------------------------
    def meta(self, room: Room) -> dict[str, Any]:
        """Everything about a room that isn't the game itself (for restoring it after a restart)."""
        return {
            "mode": room.mode, "code": room.code, "host_token": room.host_token, "host_seat": room.host_seat,
            "password_salt": room.password_salt.hex() if room.password_salt else None,
            "password_hash": room.password_hash.hex() if room.password_hash else None,
            "seats": {pid: {"token": s.token, "claimed_name": s.claimed_name} for pid, s in room.seats.items()},
            "spectator_tokens": sorted(room.spectator_tokens), "result_id": room.result_id, "created_at": room.created_at,
            "night": room.night.meta(),
        }

    def persist(self, room: Room) -> None:
        """Store the room's seats and tokens (started tables only)."""
        if self.journal is None or not room.started or room.practice is not None:
            return
        try:
            self.journal.save_meta(room.id, self.meta(room))
        except Exception:  # noqa: BLE001 - recovery data must never break play; it is logged loudly
            log.exception("Could not store room %s for recovery", room.id)

    def track(self, room: Room) -> None:
        """Journal every change of a started table (do / undo / redo) until its next checkpoint."""
        if self.journal is None or room.game is None:
            return
        journal = self.journal
        gid = room.id

        def record(kind: str, action: Any) -> None:
            entry: dict[str, Any] = {"k": kind}
            if action is not None:
                entry["a"] = action.model_dump(mode="json")
            journal.append(gid, entry)

        room.game.history.listener = record
        self.persist(room)

    def restore(self, meta: dict[str, Any], session: GameSession, client_actions: dict[str, str]) -> Room:
        """Put a recovered table back: same id, room code, seats and tokens."""
        room = Room(mode=meta["mode"], code=meta["code"], host_token=meta["host_token"], game_id=session.state.id)
        room.game = session
        room.host_seat = meta.get("host_seat")
        if meta.get("password_salt") and meta.get("password_hash"):
            room.password_salt = bytes.fromhex(meta["password_salt"])
            room.password_hash = bytes.fromhex(meta["password_hash"])
        for pid in session.state.seat_order:
            info = (meta.get("seats") or {}).get(pid) or {}
            room.seats[pid] = Seat(player_id=pid, token=info.get("token"), claimed_name=info.get("claimed_name"),
                                   last_seen=time.time())
        room.spectator_tokens = set(meta.get("spectator_tokens") or [])
        room.result_id = meta.get("result_id")
        room.night = Night.from_meta(meta.get("night"))
        room.created_at = float(meta.get("created_at") or time.time())
        room.client_actions = dict(client_actions)
        if any(r.code == room.code for r in self.rooms.values()):
            room.code = self._new_code()
        self.rooms[room.id] = room
        self.track(room)
        follow_rules(room)  # -- rules result -- a table the rules had ended asks for its result again
        return room

    def remember_action(self, room: Room, client_action_id: str, outcome: str) -> None:
        room.client_actions[client_action_id] = outcome
        if len(room.client_actions) > 512:
            for key in list(room.client_actions)[: len(room.client_actions) - 512]:
                del room.client_actions[key]
        if self.journal is not None and room.started:
            try:
                self.journal.remember_action(room.id, client_action_id, outcome)
            except Exception:  # noqa: BLE001 - see persist()
                log.exception("Could not store client action id for %s", room.id)

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

    def reissue_seat(self, room: Room, pid: str) -> str:
        """Give a seat a fresh token (host tool): the old one stops working at once."""
        token = secrets.token_urlsafe(24)
        room.seats[pid].token = token
        self.persist(room)
        return token

    async def drop_connections(self, room: Room, pid: str, *, code: int, reason: str) -> int:
        """Close every socket of a seat. Code 4000 makes clients reconnect; 4403 stops them."""
        conns = [c for c in room.connections.values() if c.viewer == pid]
        for conn in conns:
            self.disconnect(room, conn)
            if conn.close is not None:
                try:
                    await conn.close(code, reason)
                except Exception:  # noqa: BLE001 - already gone
                    log.debug("socket %s already closed", conn.id)
        return len(conns)

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
        room.night.remap(mapping)
        room.host_seat = mapping.get(room.host_seat or "")
        room.game = session
        room.phase = "playing"
        room.lobby_seats = {}
        follow_rules(room)  # -- rules result -- a fresh game forgets the last one's ending
        self.track(room)

    # -- seats -----------------------------------------------------------------------
    def claim_seat(self, room: Room, *, name: str | None, seat: str | None, spectate: bool = False) -> tuple[str, str]:
        """Claim a free seat (or become a spectator). Returns (viewer, token)."""
        token = secrets.token_urlsafe(24)
        if spectate:
            room.spectator_tokens.add(token)
            self.persist(room)
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
        self.persist(room)
        return chosen.player_id, token

    # -- live connections ------------------------------------------------------------
    def connect(self, room: Room, conn: Connection) -> None:
        room.connections[conn.id] = conn
        if conn.viewer in room.seats:
            room.seats[conn.viewer].connections += 1

    def disconnect(self, room: Room, conn: Connection) -> None:
        if room.connections.pop(conn.id, None) is not None and conn.viewer in room.seats:
            seat = room.seats[conn.viewer]
            seat.connections = max(0, seat.connections - 1)
            if seat.connections == 0:
                seat.last_seen = time.time()

    async def broadcast(self, room: Room, *, resync: bool = False) -> None:
        """Send each connection a fresh view built for its own viewer (a new revision)."""
        room.revision += 1
        cache: dict[str, dict[str, Any]] = {}
        stale: list[Connection] = []
        for conn in list(room.connections.values()):
            key = f"{conn.viewer}:{conn.host}"
            message = cache.get(key)
            if message is None:
                message = cache[key] = self.message(room, conn.viewer, host=conn.host)
                if resync:
                    message = cache[key] = {**message, "resync": True}
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
        return {"type": "state", "view": self.view(room, viewer), "revision": room.revision}

    def _assets(self, room: Room) -> dict[str, Any]:
        if self.asset_info is None or room.game is None:
            return {}
        st = room.game.state
        ids = {p.sleeve for p in st.players.values() if p.sleeve}
        ids |= {p.playmat.asset_id for p in st.players.values() if p.playmat}
        if st.table.playmat:
            ids.add(st.table.playmat.asset_id)
        return self.asset_info(ids) if ids else {}

    def view(self, room: Room, viewer: str) -> dict[str, Any]:
        room.pulse.observe(room.session.state, room.night.number, room.night.result, room.seat_name)
        host = room.mode == "local" or (room.host_seat is not None and viewer == room.host_seat)
        meta = {
            "mode": room.mode,
            "code": room.code if room.mode == "lan" else None,
            "seats": {pid: s.public() for pid, s in room.seats.items()},
            "host_seat": room.host_seat,
            "revision": room.revision,
            "result_id": room.result_id,
            "assets": self._assets(room),
            "night": room.night.public(room.seat_name),
            # -- undo policy (gap 3) -- the host's own seat at a LAN table, anyone at a hot-seat one (as the API decides)
            **undo_rights.view_fields(room.session.state, room.session.history, host=host),
            # -- quick undo request -- the request waiting for the table, and whether this viewer's undo would ask it
            **undo_requests.view_fields(room.session, viewer, host=host, others=undo_voters(room, viewer)),
            "events": room.pulse.public(),
        }
        if room.practice is not None:  # a practice table has no code to share and no game night of its own
            meta.update(code=None, practice=room.practice.public())
            del meta["night"]
        return room.session.view(viewer, meta=meta)

    def after_change(self, room: Room) -> None:
        follow_rules(room)  # -- rules result -- the engine ended the game (or an undo took that back)
        self.persist(room)
        room.actions_since_save += 1
        if self._autosave and room.actions_since_save >= self.autosave_every:
            room.actions_since_save = 0
            try:
                self._autosave(room)
            except Exception:  # noqa: BLE001 - autosave failure must not break play; it is logged loudly
                log.exception("Autosave failed for game %s", room.id)


def undo_voters(room: Room, actor: str | None) -> list[str] | None:
    """-- quick undo request -- who approves an undo request from ``actor``: every other seated player still in the game (a LAN
    seat nobody has taken can't answer). None at a hot-seat table, where undo stays direct (app/game/undo_requests.py)."""
    if room.mode == "local" or room.game is None or actor not in room.seats:
        return None
    return [pid for pid in undo_requests.still_in(room.game.state)
            if pid != actor and pid in room.seats and room.seats[pid].token is not None]


def valid_viewer(room: Room, viewer: str) -> bool:
    return viewer in room.seats or viewer in (SPECTATOR, OMNISCIENT)
