"""Game rooms, seats and live connections (host-authoritative).

* **local** rooms are hot-seat tables. Any *loopback* client may view or act as any seat
  (and use the omniscient "open table" view). They are never reachable from the LAN.
* **lan** rooms require a seat token. A token is issued when a seat is claimed (with the
  room code and optional password) and is used to reconnect. Every connection receives a
  view built for its own seat; spectators get the public view.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import logging
import secrets
import threading
import time
from collections.abc import Awaitable, Callable
from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from app.game import undo_requests, undo_rights
from app.game.actions import INTENT_TYPES, Action
from app.game.factory import PLAYER_COLORS
from app.game.ops import down_public
from app.game.session import GameSession
from app.game.summary import player_commanders
from app.game.visibility import OMNISCIENT, SPECTATOR
from app.multiplayer import (
    bots,  # -- test opponent -- the server's pacing of its actions
    response_call,  # -- I have a response / flip the table --
    view_delta,  # -- view deltas --
)
from app.multiplayer.elimination import PracticeLink, Pulse
from app.multiplayer.lobby import LobbySeatInfo, LobbySettings, deck_summary
from app.multiplayer.night import Night, follow_rules, rematch_missing
from app.multiplayer.spectate import Predictions
from app.storage.journal import MAX_CLIENT_ACTIONS, RoomJournal

if TYPE_CHECKING:
    from app.decks.repository import DeckRepository

log = logging.getLogger(__name__)

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
Mode = Literal["local", "lan"]
Phase = Literal["lobby", "playing"]
SendFn = Callable[[dict[str, Any]], Awaitable[None]]


PASSWORD_ROUNDS = 600_000  # what a password is hashed at now (OWASP's figure for PBKDF2-HMAC-SHA256)
MAX_SPECTATORS = 32  # spectator tokens per room; a join past it lets the earliest one go
MAX_STORED_ROUNDS = 10_000_000  # a saved count above this is not ours: one join must not burn minutes of CPU on a doctored file
# At most 4 hashes run at once: this bounds the CPU hashing costs. /api/join counts a guess against the address before hashing it (a
# burst from one address is refused from the sixth on, unhashed) and hashes on ``Services.hash_pool`` (4 threads of its own), so joins
# waiting to be checked never hold the threads the other sync routes share. Room creation still hashes on a shared worker thread; the
# slots keep it and the joins at 4 together.
_hash_slots = threading.BoundedSemaphore(4)


def _pbkdf2(password: str, salt: bytes, rounds: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)


def _hash_password(password: str, salt: bytes, rounds: int) -> bytes:
    """Every password hash passes here (room creation, checks and the unknown-code stand-in), 4 at a time."""
    with _hash_slots:
        return _pbkdf2(password, salt, rounds)


def _rounds_ok(rounds: object) -> bool:
    return type(rounds) is int and 1 <= rounds <= MAX_STORED_ROUNDS


_NO_ROOM_SALT = bytes(16)


def spend_password_check(password: str | None) -> None:
    """The cost of checking a password against a room, for a room code that has none, so a wrong code answers as slowly as a wrong password."""
    _hash_password(password or "", _NO_ROOM_SALT, PASSWORD_ROUNDS)


RECONNECT_GRACE = 60.0  # seconds a dropped player shows as "Reconnecting…" before "Disconnected"
Presence = Literal["open", "connected", "reconnecting", "disconnected"]


BOT_TOKEN = "bot:"  # -- LAN bots -- the token of a seat a bot plays (the server's own: never sent, never a person's)


def bot_token() -> str:
    return BOT_TOKEN + secrets.token_urlsafe(18)


@dataclass
class Seat:
    player_id: str
    token: str | None = None
    claimed_name: str | None = None
    connections: int = 0
    last_seen: float | None = None  # when the last connection of this seat dropped

    @property
    def bot(self) -> bool:
        """-- LAN bots -- the server plays this seat (a bot the host seated in the lobby)."""
        return (self.token or "").startswith(BOT_TOKEN)

    def presence(self, now: float | None = None) -> Presence:
        if self.bot:
            return "connected"  # (it is always there)
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
    host: bool = False  # connected with host rights (lobby management): never through the tunnel (app/api/deps.py room_host)
    tunnel: bool = False  # -- invite over the internet -- connected on the tunnel port (app/api/deps.py is_tunnel_request)
    token: str | None = field(default=None, repr=False)  # the seat token it authenticated with (a secret: never logged)
    close: Callable[[int, str], Awaitable[None]] | None = None  # drop this socket (the client reconnects)
    id: str = field(default_factory=lambda: secrets.token_hex(4))
    # -- view deltas (app/multiplayer/view_delta.py) -- the client applies patches (its auth message asked: ``deltas``): after a full view, each
    # update is the patch from the last view sent here (``sent``, as the client parsed it), naming it by its number on this connection
    # (``vseq``: every view message sent here counts). None: no view to patch (none sent yet, or a lobby since)
    deltas: bool = False
    sent: dict[str, Any] | None = field(default=None, repr=False)
    vseq: int = 0


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
    password_rounds: int = 120_000  # (the default is what metadata written before this field used)
    _password_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)  # the three password fields change together
    seats: dict[str, Seat] = field(default_factory=dict)
    spectator_tokens: list[str] = field(default_factory=list)  # oldest first, at most MAX_SPECTATORS
    dropped_spectators: list[str] = field(default_factory=list)  # tokens let go by the cap, their sockets not yet closed (memory only)
    connections: dict[str, Connection] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    actions_since_save: int = 0
    created_at: float = field(default_factory=time.time)
    revision: int = 0  # bumped on every authoritative update sent to clients
    result_id: str | None = None  # the recorded pod result for this game, if any
    # actor (the seat an action is performed as) -> client_action_id -> outcome ("ACCEPTED" / "REJECTED: …"): a retried action applies
    # once. Scoped to the seat: one seat's ids never match, evict or reveal another's.
    client_actions: dict[str, dict[str, str]] = field(default_factory=dict)
    night: Night = field(default_factory=Night)  # game night: turn order, agreed endings, rematch vote
    pulse: Pulse = field(default_factory=Pulse)  # major public events of the current game (elimination hub)
    practice: PracticeLink | None = None  # a private practice table (elimination hub): whose it is
    shared: bool = False  # -- invite over the internet -- served on the tunnel port (app/api/deps.py tunnel_serves)
    invite_code: str | None = None  # -- invite over the internet -- what the tunnel port takes in place of ``code`` (never in a view)
    predictions: Predictions = field(default_factory=Predictions)  # spectators' fake-point predictions (memory only)
    saved_rows: dict[str, dict[str, str]] = field(default_factory=dict)  # -- saved rows -- deck id -> the rows last stored for it
    # -- resolving progress -- a rules intent being worked out off the event loop (``GameHub.perform``): done once it is applied.
    # Readers of the table outside the room lock wait for it (``GameHub.settled``).
    acting: asyncio.Future[None] | None = None

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

    def password_state(self) -> tuple[bytes | None, bytes | None, int]:
        with self._password_lock:
            return self.password_salt, self.password_hash, self.password_rounds

    def check_password(self, password: str | None, on_upgrade: Callable[[], None] | None = None) -> bool:
        """Does the password match? A right one on a hash made with fewer rounds than ``PASSWORD_ROUNDS`` re-hashes it
        (new salt) and calls ``on_upgrade`` so the caller can store the room."""
        salt, stored, rounds = self.password_state()
        if stored is None or salt is None:
            return True
        if not _rounds_ok(rounds):  # (a damaged or doctored saved count: this room verifies nothing, at the cost of a current room's check)
            _hash_password(password or "", salt, PASSWORD_ROUNDS)
            return False
        if not hmac.compare_digest(_hash_password(password or "", salt, rounds), stored):
            return False
        if rounds < PASSWORD_ROUNDS:
            new_salt = secrets.token_bytes(16)
            new_hash = _hash_password(password or "", new_salt, PASSWORD_ROUNDS)
            with self._password_lock:
                upgraded = self.password_hash == stored and self.password_salt == salt  # (else a join at the same moment already did)
                if upgraded:
                    self.password_salt, self.password_hash, self.password_rounds = new_salt, new_hash, PASSWORD_ROUNDS
            if upgraded and on_upgrade is not None:
                on_upgrade()
        return True

    def seat_for_token(self, token: str | None) -> str | None:
        """Player id for a seat token, SPECTATOR for a spectator token, else None."""
        if not token or not token.isascii() or token.startswith(BOT_TOKEN):  # (compare_digest raises on a non-ASCII str)
            return None  # (-- LAN bots -- nobody acts as a bot: the server plays it directly)
        for seat in self.seats.values():
            if seat.token and hmac.compare_digest(seat.token, token):
                return seat.player_id
        if any(hmac.compare_digest(t, token) for t in self.spectator_tokens):
            return SPECTATOR
        return None

    def is_host(self, token: str | None) -> bool:
        """The host token, or the seat token of the host's own seat."""
        if not token or not token.isascii():
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

    def summary(self, *, commanders: bool = False) -> dict[str, Any]:
        """The table at a glance. ``commanders`` adds each player's commanders and seat colour once the game has started (public:
        they began face up in the command zone), for the Play page's tiles."""
        common = {
            "id": self.game_id,
            "mode": self.mode,
            "phase": self.phase,
            "code": self.code if self.mode == "lan" else None,
            "shared": self.shared,
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
                        "connected": s.connections > 0 or s.bot,  # (-- LAN bots -- always at the table, never "away")
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
                    # (-- target dummy -- and -- test opponent --: nobody's seat to join, and never "away")
                    "claimed": self.seats[pid].token is not None or st.players[pid].dummy or st.players[pid].bot is not None,
                    "connected": self.seats[pid].connections > 0 or self.seats[pid].bot or st.players[pid].dummy
                    or st.players[pid].bot is not None,
                    **({"color": st.players[pid].color, "commanders": player_commanders(st, pid)} if commanders else {}),
                }
                for pid in st.seat_order
            ],
            "updated_at": self.game.updated_at,
        }

    # -- lobby -----------------------------------------------------------------------
    def claimed_seats(self) -> list[str]:
        """The lobby seats someone has taken, in seating order (seat 1 first): the order the next game seats them in."""
        return [pid for pid, seat in self.seats.items() if seat.token is not None]

    def last_winner_seat(self) -> str | None:
        """The lobby seat of the last game's single winner (who goes last under the pod rule), if they are still seated."""
        key = self.night.last_winner_key
        return next((pid for pid, seat in self.seats.items() if key and seat.token == key), None)

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
                    **({"bot": info.bot or "intermediate"} if seat.bot else {}),  # -- LAN bots -- its level (public)
                    "deck": deck_summary(info.deck, privacy=settings.deck_privacy, own=pid == viewer, table_format=settings.format),
                    # (spectator activities) the deck this player queued while out of the last game, still unchanged
                    **({"queued": True} if pid == viewer and info.deck is not None and info.deck is info.queued else {}),
                }
            )
        return {
            "game": {
                "id": self.game_id,
                "mode": self.mode,
                "code": self.code if self.mode == "lan" else None,
                "shared": self.shared,
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
            # -- seating -- the next game's order as far as it is known before the start (public)
            "turn_preview": Night.preview(self.claimed_seats(), self.last_winner_seat(), settings.turn_order),
        }

    def start_blockers(self) -> list[str]:
        """Why the host can't start yet without overriding (empty when everyone is ready)."""
        claimed = [pid for pid, s in self.seats.items() if s.token is not None]
        if not claimed:
            return ["Nobody has taken a seat"]
        out = []
        settings = self.lobby or LobbySettings()
        policy = settings.policy()
        if policy is not None and policy.needs_definition:
            out.append(f"The {policy.display_name} mulligan isn't defined yet (Table settings)")
        for pid in claimed:
            info = self.lobby_seats.get(pid) or LobbySeatInfo()
            if self.seats[pid].bot and settings.automation != "full":
                out.append(f"{self.seat_name(pid)} is a bot: it plays only with rules automation at Full (Table settings)")
            if info.deck is None:
                out.append(f"{self.seat_name(pid)} hasn't chosen a deck")
            elif not info.ready:
                out.append(f"{self.seat_name(pid)} isn't ready")
        return out


class GameHub:
    def __init__(self, *, autosave: Callable[[Room], None] | None = None, autosave_every: int = 10,
                 asset_info: Callable[[set[str]], dict[str, Any]] | None = None, journal: RoomJournal | None = None,
                 decks: DeckRepository | None = None) -> None:
        self.rooms: dict[str, Room] = {}
        self.journal = journal
        self.decks = decks  # -- saved rows -- where rows learned at the table are stored
        self.asset_info = asset_info  # asset id -> {url, width, height} for sleeves / playmats in views
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
            room.password_hash = _hash_password(password, room.password_salt, PASSWORD_ROUNDS)
            room.password_rounds = PASSWORD_ROUNDS
        return room

    def _new_code(self) -> str:
        while True:
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
            if all(r.code != code for r in self.rooms.values()):
                return code

    def new_invite_code(self, room: Room) -> str:
        """The room's invite code (10 characters, unique against every room's codes), made once per share: sharing again while shared
        keeps it; stopping sharing clears it (Services._end_share), so the next share has a new one."""
        if room.invite_code is None:
            taken = {c for r in self.rooms.values() for c in (r.code, r.invite_code)}
            while True:
                code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(10))
                if code not in taken:
                    room.invite_code = code
                    self.persist(room)
                    break
        return room.invite_code

    def set_password(self, room: Room, password: str) -> None:
        """Give the room a new password (new salt, current rounds) and store the room."""
        if not password:
            raise ValueError("A room password cannot be empty")
        salt = secrets.token_bytes(16)
        new_hash = _hash_password(password, salt, PASSWORD_ROUNDS)
        with room._password_lock:
            room.password_salt, room.password_hash, room.password_rounds = salt, new_hash, PASSWORD_ROUNDS
        self.persist(room)

    def get(self, game_id: str) -> Room | None:
        return self.rooms.get(game_id)

    def by_code(self, code: str) -> Room | None:
        code = code.strip().upper()
        if not code.isascii():  # (compare_digest raises on a non-ASCII str)
            return None
        return next((r for r in self.rooms.values() if r.mode == "lan" and r.practice is None and hmac.compare_digest(r.code, code)), None)

    def by_invite_code(self, code: str) -> Room | None:
        """The shared LAN room this invite code opens (the tunnel port's way in; ``by_code`` never matches one)."""
        code = code.strip().upper()
        if not code.isascii():  # (compare_digest raises on a non-ASCII str)
            return None
        return next((r for r in self.rooms.values() if r.shared and r.invite_code is not None and r.mode == "lan" and r.practice is None
                     and hmac.compare_digest(r.invite_code, code)), None)

    def close(self, game_id: str) -> None:
        room = self.rooms.pop(game_id, None)
        bots.forget(game_id)
        response_call.forget(game_id)
        if room:
            if room.game is not None:
                room.game.history.listener = None
            log.info("Closed room %s", game_id)
        if self.journal is not None:
            self.journal.forget(game_id)

    # -- crash recovery --------------------------------------------------------------
    def meta(self, room: Room) -> dict[str, Any]:
        """Everything about a room that isn't the game itself (for restoring it after a restart)."""
        salt, pw_hash, rounds = room.password_state()
        return {
            "mode": room.mode, "code": room.code, "invite_code": room.invite_code, "shared": room.shared, "host_token": room.host_token, "host_seat": room.host_seat,
            "password_salt": salt.hex() if salt else None,
            "password_hash": pw_hash.hex() if pw_hash else None,
            "password_rounds": rounds,
            "seats": {pid: {"token": s.token, "claimed_name": s.claimed_name} for pid, s in room.seats.items()},
            "spectator_tokens": list(room.spectator_tokens), "result_id": room.result_id, "created_at": room.created_at,
            "night": room.night.meta(),
            "lobby": room.lobby.model_dump(mode="json") if room.lobby is not None else None,  # (the pod rule, mulligans… for the next game)
        }

    def persist(self, room: Room) -> None:
        """Store the room's seats and tokens (started tables only)."""
        if self.journal is None or not room.started or room.practice is not None:
            return
        try:
            self.journal.save_meta(room.id, self.meta(room))
        except Exception:  # noqa: BLE001 - recovery data must never break play; it is logged loudly
            log.exception("Could not store room %s for recovery", room.id)

    def save_rows(self, room: Room) -> None:
        """-- saved rows -- store each saved deck's rows as the table now has them (learned by set_position, app/game/resolve.py),
        outside the replayed game: an undo that takes a move back takes its lesson back here too. A deck brought from another
        computer has no deck id; its rows last for this game only."""
        if self.decks is None or room.game is None or room.practice is not None:
            return
        for p in room.game.state.players.values():
            if not p.deck_id:
                continue
            try:
                if p.deck_id not in room.saved_rows:
                    room.saved_rows[p.deck_id] = self.decks.row_overrides(p.deck_id)
                rows = {k: str(v) for k, v in p.row_overrides.items()}
                if rows != room.saved_rows[p.deck_id]:
                    self.decks.set_row_overrides(p.deck_id, rows)
                    room.saved_rows[p.deck_id] = rows
            except Exception:  # noqa: BLE001 - a deck deleted mid-game (or a busy database) must never break play
                log.warning("Could not store the saved rows of deck %s", p.deck_id, exc_info=True)
                room.saved_rows[p.deck_id] = {k: str(v) for k, v in p.row_overrides.items()}

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

    def restore(self, meta: dict[str, Any], session: GameSession, client_actions: dict[str, dict[str, str]]) -> Room:
        """Put a recovered table back: same id, room code, seats and tokens."""
        room = Room(mode=meta["mode"], code=meta["code"], host_token=meta["host_token"], game_id=session.state.id)
        room.game = session
        room.host_seat = meta.get("host_seat")
        room.invite_code = meta.get("invite_code")  # (shared stays False: closing Fyodor ends the link)
        if meta.get("password_salt") and meta.get("password_hash"):
            room.password_salt = bytes.fromhex(meta["password_salt"])
            room.password_hash = bytes.fromhex(meta["password_hash"])
            rounds = meta.get("password_rounds", room.password_rounds)
            room.password_rounds = rounds if _rounds_ok(rounds) else 0  # (a bad count keeps the room locked: check_password refuses it)
        for pid in session.state.seat_order:
            info = (meta.get("seats") or {}).get(pid) or {}
            room.seats[pid] = Seat(player_id=pid, token=info.get("token"), claimed_name=info.get("claimed_name"),
                                   last_seen=time.time())
        # (a list in join order; one written before the cap is sorted or set-like: its last ones are kept, not necessarily the newest)
        room.spectator_tokens = list(meta.get("spectator_tokens") or [])[-MAX_SPECTATORS:]
        room.result_id = meta.get("result_id")
        room.night = Night.from_meta(meta.get("night"))
        if meta.get("lobby"):
            room.lobby = LobbySettings.model_validate(meta["lobby"])
        room.created_at = float(meta.get("created_at") or time.time())
        room.client_actions = {actor: dict(ids) for actor, ids in client_actions.items()}
        if any(r.code == room.code for r in self.rooms.values()):
            room.code = self._new_code()
        if room.invite_code is not None and any(room.invite_code in (r.code, r.invite_code) for r in self.rooms.values()):
            room.invite_code = None
        self.rooms[room.id] = room
        self.track(room)
        follow_rules(room)  # -- rules result -- a table the rules had ended asks for its result again
        return room

    def remember_action(self, room: Room, actor: str, client_action_id: str, outcome: str) -> None:
        """Remember what became of ``actor``'s action; at most ``MAX_CLIENT_ACTIONS`` per seat, the seat's own oldest go first."""
        mine = room.client_actions.setdefault(actor, {})
        mine[client_action_id] = outcome
        for key in list(mine)[: max(0, len(mine) - MAX_CLIENT_ACTIONS)]:
            del mine[key]
        if self.journal is not None and room.started:
            try:
                self.journal.remember_action(room.id, actor, client_action_id, outcome)
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
        if room.seats[pid].bot:
            raise PermissionError("A bot plays that seat")
        token = secrets.token_urlsafe(24)
        room.seats[pid].token = token
        self.persist(room)
        return token

    async def drop_connections(self, room: Room, pid: str, *, code: int, reason: str) -> int:
        """Close every socket of a seat. Code 4000 makes clients reconnect; 4403 stops them."""
        return await self._close_all(room, [c for c in room.connections.values() if c.viewer == pid], code, reason)

    async def _close_all(self, room: Room, conns: list[Connection], code: int, reason: str) -> int:
        for conn in conns:
            self.disconnect(room, conn)
            if conn.close is not None:
                try:
                    await conn.close(code, reason)
                except Exception:  # noqa: BLE001 - already gone
                    log.debug("socket %s already closed", conn.id)
        return len(conns)

    async def close_seat_connections(self, room: Room, player_id: str, reason: str) -> None:
        """A seat's token was replaced or the seat was taken away: close that seat's sockets that do not hold the seat's current token at
        once with 4403 (clients stop, they do not reconnect). A seat with no token any more loses all of them; a socket with no token
        on a seat (none exists in a LAN game) counts as not holding it. Only this seat's: never another seat's."""
        current = room.seats[player_id].token if player_id in room.seats else None
        stale = [c for c in room.connections.values()
                 if c.viewer == player_id and (current is None or c.token is None or not hmac.compare_digest(c.token, current))]
        await self._close_all(room, stale, 4403, reason)

    async def close_tunnel_connections(self, room: Room, reason: str) -> int:
        """-- invite over the internet -- close, with 4403, every socket of the room that came in through the tunnel (the table is no
        longer shared); the LAN's are untouched."""
        return await self._close_all(room, [c for c in room.connections.values() if c.tunnel], 4403, reason)

    async def close_dropped_spectators(self, room: Room) -> None:
        """Close, with 4403, the sockets of spectators the cap let go, and forget them."""
        dropped, room.dropped_spectators = room.dropped_spectators, []
        stale = [c for c in room.connections.values()
                 if c.token is not None and any(hmac.compare_digest(c.token, t) for t in dropped)]
        await self._close_all(room, stale, 4403, "Too many spectators: the earliest one was let go.")

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

    def arrange_seats(self, room: Room, order: list[str]) -> None:
        """-- seating -- the host arranges the lobby: ``order`` lists every seat, the one to sit at seat 1 first. Each player
        keeps their token, name, deck, readiness and chosen colour (an unchosen one is the seat's, as when a player moves
        seat themselves); their open connections follow them."""
        if sorted(order) != sorted(room.seats):
            raise LookupError("List every seat once")
        mapping = {old: f"p{i + 1}" for i, old in enumerate(order)}
        seats: dict[str, Seat] = {}
        infos: dict[str, LobbySeatInfo] = {}
        for old, new in mapping.items():
            seat = room.seats[old]
            seats[new] = Seat(player_id=new, token=seat.token, claimed_name=seat.claimed_name, connections=seat.connections,
                              last_seen=seat.last_seen)
            infos[new] = room.lobby_seats.get(old) or LobbySeatInfo()
        for conn in room.connections.values():
            if conn.viewer in mapping:
                conn.viewer = mapping[conn.viewer]
                conn.actor = conn.viewer if conn.actor is not None else None
        room.seats, room.lobby_seats = seats, infos
        room.host_seat = mapping.get(room.host_seat or "", room.host_seat)

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
            room.spectator_tokens.append(token)
            while len(room.spectator_tokens) > MAX_SPECTATORS:  # (the earliest is let go; join_game closes its sockets)
                dropped = room.spectator_tokens.pop(0)
                room.night.queued.pop(dropped, None)
                room.dropped_spectators.append(dropped)
            self.persist(room)
            return SPECTATOR, token
        state = room.game.state if room.game is not None else None
        nobody = {pid for pid, p in state.players.items() if p.dummy or p.bot is not None} if state is not None else set()  # -- target dummy -- (and -- test opponent --) nobody sits there
        left = {pid for pid, p in state.players.items() if p.left} if state is not None else set()  # -- removed player -- their seat is gone, not free
        free = [s for s in room.seats.values() if s.token is None and s.player_id not in nobody and s.player_id not in left]
        if seat is not None:
            chosen = room.seats.get(seat)
            if chosen is None:
                raise LookupError("No such seat")
            if seat in nobody:
                raise PermissionError("That seat is the target dummy's" if state is not None and state.players[seat].dummy
                                      else "That seat is the test opponent's")
            if seat in left:
                raise PermissionError("That player has left the table")
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
        bots.poke(self, room)  # -- test opponent -- a table created or loaded off the event loop starts playing when someone sits down

    def disconnect(self, room: Room, conn: Connection) -> None:
        if room.connections.pop(conn.id, None) is not None and conn.viewer in room.seats:
            seat = room.seats[conn.viewer]
            seat.connections = max(0, seat.connections - 1)
            if seat.connections == 0:
                seat.last_seen = time.time()

    # -- resolving progress --------------------------------------------------------------
    async def perform(self, room: Room, actor: str, payload: dict[str, Any], *, host: bool = False) -> Action:
        """One player action (the caller holds the room lock). A rules intent is worked out off the event loop, on the table's scratch
        copy (``GameSession.prepare``): while a long automatic chain runs (200 end-step sacrifices), every connection is sent interim
        views of it as it goes, each built for its own viewer by the same builders as every update; then the action is applied and
        recorded as one, as always (``commit``, on the loop). Interim views are display only: no revision, no history, no replay; the
        broadcast after the action is the table's word. Anything else is performed at once, as before."""
        session = room.session
        if payload.get("type") not in INTENT_TYPES or session.state.rules is None or not room.connections:
            done = False
            try:
                action = session.perform(actor, payload, host=host)
                done = True
                return action
            finally:
                response_call.after(self, room, actor, payload, applied=done)  # -- I have a response / flip the table --
        loop = asyncio.get_running_loop()
        stream = InterimStream(self, room, loop, actor)
        stream.calls = response_call.pending(room)  # -- I have a response -- a hold heard while this is worked out stops its chain
        room.acting = loop.create_future()
        applied = False
        try:
            try:
                prepared = await asyncio.to_thread(session.prepare, actor, payload, host=host, watcher=stream.watch)
            finally:
                await stream.close()  # (nothing interim is sent after this: the action's own update comes next)
            resolved = session.commit(prepared)
            applied = True
            return resolved
        finally:
            done, room.acting = room.acting, None
            if done is not None and not done.done():
                done.set_result(None)
            response_call.after(self, room, actor, payload, applied=applied)  # -- I have a response / flip the table --
            if not applied and stream.sent:  # refused or failed after interim views went out: everyone back to the table as it is
                await self.broadcast(room, resync=True)

    async def settled(self, room: Room) -> None:
        """Wait until no action is being worked out off the event loop (``perform``): then the table is read as it is."""
        while (acting := room.acting) is not None:
            await asyncio.shield(acting)

    def interim_metas(self, room: Room) -> dict[str, tuple[str, dict[str, Any]]]:
        """-- resolving progress -- (on the event loop) each connection's viewer and the room's part of its view, as ``view`` builds it."""
        out: dict[str, tuple[str, dict[str, Any]]] = {}
        for conn in list(room.connections.values()):
            key = f"{conn.viewer}:{conn.host}"
            if key not in out:
                out[key] = (conn.viewer, self._meta(room, conn.viewer))
        return out

    async def broadcast(self, room: Room, *, resync: bool = False, viewer: str | None = None) -> dict[str, Any] | None:
        """Send each connection a fresh view built for its own viewer (a new revision). ``viewer``: also build (or reuse) that
        viewer's view in the same pass and return it, for the HTTP reply to whoever acted (built after the sends, it would be the
        table worked out a second time)."""
        await self.settled(room)  # -- resolving progress -- (an action being worked out: its table, once applied)
        room.revision += 1
        cache: dict[str, dict[str, Any]] = {}
        stale: list[Connection] = []
        conns = list(room.connections.values())
        reply: dict[str, Any] | None = None
        # -- big boards (views) -- every view is built before any is sent (no await in between: all of the same table), in one read pass:
        # what each view derives, every permanent's characteristics, is worked out once for the table, not once per viewer
        with room.session.reading() if room.started else nullcontext():
            for conn in conns:
                key = f"{conn.viewer}:{conn.host}"
                if key not in cache:
                    message = self.message(room, conn.viewer, host=conn.host)
                    cache[key] = {**message, "resync": True} if resync else message
            if viewer is not None and room.started:
                reply = next((m["view"] for k, m in cache.items() if k.split(":", 1)[0] == viewer), None) or self.view(room, viewer)
        frozen: dict[str, tuple[dict[str, Any], str]] = {}  # -- view deltas -- each view as clients parse it, each patch: worked out once
        patches: dict[tuple[int, str], tuple[dict[str, Any], dict[str, Any] | None]] = {}
        for conn in conns:
            key = f"{conn.viewer}:{conn.host}"
            message = cache[key]
            if conn.deltas:
                message = self._update(conn, key, message, frozen, patches, full=resync)
            try:
                await conn.send(message)
            except Exception as exc:  # noqa: BLE001 - a dead socket must not break the table for others
                log.info("Dropping connection %s: %s", conn.id, exc)
                stale.append(conn)
        for conn in stale:
            self.disconnect(room, conn)
        bots.poke(self, room)  # -- test opponent -- its next action, if the game waits for it
        return reply

    async def send_to(self, room: Room, viewer: str, message: dict[str, Any]) -> None:
        for conn in [c for c in room.connections.values() if c.viewer == viewer]:
            try:
                await conn.send(message)
            except Exception:  # noqa: BLE001 - best effort
                self.disconnect(room, conn)

    # -- view deltas --------------------------------------------------------------------------
    def full(self, conn: Connection, message: dict[str, Any]) -> dict[str, Any]:
        """A full view (or lobby) message about to be sent to ``conn`` outside a broadcast (its first view, a resync, a seat switch): the
        view the next update is a patch from."""
        return self._update(conn, f"{conn.viewer}:{conn.host}", message, {}, {}, full=True) if conn.deltas else message

    def _update(self, conn: Connection, key: str, message: dict[str, Any], frozen: dict[str, tuple[dict[str, Any], str]],
                patches: dict[tuple[int, str], tuple[dict[str, Any], dict[str, Any] | None]], *, full: bool) -> dict[str, Any]:
        """What ``conn`` is sent for ``message`` (built for its viewer): the view itself, or the patch from the last view it was sent. Called
        right before the send, so the numbers go out in the order they were given."""
        if message.get("type") != "state" or not isinstance(message.get("view"), dict):
            conn.sent = None  # (a lobby: the game's first view is whole)
            return message
        got = frozen.get(key)
        if got is None:
            got = frozen[key] = view_delta.freeze(message["view"])
        view, text = got
        base, base_seq = conn.sent, conn.vseq
        conn.sent, conn.vseq = view, conn.vseq + 1
        if full or base is None:
            return {**message, "vseq": conn.vseq}
        kept = patches.get((id(base), key))  # (connections with the same view had the same last view: one patch)
        if kept is None or kept[0] is not base:
            kept = patches[(id(base), key)] = (base, view_delta.checked(base, view, text))
        if kept[1] is None:  # (a patch that would not give this very view: the whole view)
            return {**message, "vseq": conn.vseq}
        return {"type": "delta", "revision": message.get("revision", view.get("game", {}).get("revision")), "base": base_seq,
                "vseq": conn.vseq, "patch": kept[1]}

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
        room.predictions.observe(room.pulse, room.night.result)  # (spectator activities) follows the same public facts
        return room.session.view(viewer, meta=self._meta(room, viewer))

    def _meta(self, room: Room, viewer: str) -> dict[str, Any]:
        """The room's part of ``viewer``'s view (seats, revision, game night, undo rights…)."""
        recap = room.predictions.recap(room.night.number, room.seat_name) if room.night.result is not None else None
        host = room.mode == "local" or (room.host_seat is not None and viewer == room.host_seat)
        meta = {
            "mode": room.mode,
            "code": room.code if room.mode == "lan" else None,
            "shared": room.shared,
            "seats": {pid: s.public() for pid, s in room.seats.items()},
            "host_seat": room.host_seat,
            "revision": room.revision,
            "result_id": room.result_id,
            "assets": self._assets(room),
            "night": {**room.night.public(room.seat_name), "rematch_missing": rematch_missing(room)},
            # -- undo policy (gap 3) -- the host's own seat at a LAN table, anyone at a hot-seat one (as the API decides)
            **undo_rights.view_fields(room.session.state, room.session.history, host=host),
            # -- quick undo request -- the request waiting for the table, and whether this viewer's undo would ask it
            **undo_requests.view_fields(room.session, viewer, host=host, others=undo_voters(room, viewer)),
            "events": room.pulse.public(),
            **({"predictions": recap} if recap else {}),
            **bots.view_fields(room),  # -- test opponent -- the top bar's bot speed
        }
        if room.night.final_board() is not None:  # -- final board -- nothing to undo or redo on a finished table
            meta.update(can_undo=False, can_redo=False)
        if room.practice is not None:  # a practice table has no code to share and no game night of its own
            meta.update(code=None, practice=room.practice.public())
            del meta["night"]
        return meta

    def after_change(self, room: Room) -> None:
        if room.game is not None:  # -- target dummy -- a seat added mid-game (or taken back by an undo) has its room seat
            state = room.game.state
            for pid in state.seat_order:
                room.seats.setdefault(pid, Seat(player_id=pid))
            for pid in [pid for pid, seat in room.seats.items() if pid not in state.players and seat.token is None]:
                del room.seats[pid]
        follow_rules(room)  # -- rules result -- the engine ended the game (or an undo took that back)
        bots.poke(self, room)  # -- test opponent -- (inside the event loop: its next action, paced)
        self.persist(room)
        self.save_rows(room)
        room.actions_since_save += 1
        if self._autosave and room.actions_since_save >= self.autosave_every:
            room.actions_since_save = 0
            try:
                self._autosave(room)
            except Exception:  # noqa: BLE001 - autosave failure must not break play; it is logged loudly
                log.exception("Autosave failed for game %s", room.id)


INTERIM_FIRST = 0.3  # seconds: an action worked out faster shows nothing in between
INTERIM_EVERY = 0.35  # seconds between two interim views, at least
INTERIM_SHARE = 3.0  # and at least this many times what building the last set took (the chain itself keeps most of the time)


class InterimStream:
    """-- resolving progress -- the interim views of one action (``GameHub.perform``). ``watch`` runs on the worker thread working the
    action out, called by the engine after each object it resolves (app/rules/progress.py): it builds each connection's view of the
    action's scratch table there (only reading it) and hands them to the event loop, which sends the newest set only (a set that
    arrives while one is being sent replaces any set still waiting). After ``close`` nothing more is sent.

    -- view deltas -- interim views are always whole, even to a client that takes deltas: they are display only, sent "latest wins" (a
    set can be dropped), at most a few a second and only during long chains; a patch chain through them would break on every drop. They
    leave ``Connection.sent`` alone: the action's own update is a patch from the last authoritative view, which the client keeps."""

    def __init__(self, hub: GameHub, room: Room, loop: asyncio.AbstractEventLoop, actor: str) -> None:
        self.hub, self.room, self.loop, self.actor = hub, room, loop, actor
        self.next_at = time.monotonic() + INTERIM_FIRST
        self.metas: dict[str, tuple[str, dict[str, Any]]] | None = None
        self.revision = room.revision  # (the update they are views on top of: a client that has a newer one drops them)
        self.closed = False
        # 406.3: a card that went face down where others see it gets its new id only at the end of the action (Plan.renumber_face_down):
        # from then on the interim messages carry the count only, no view
        self.face_down = False
        self.latest: dict[str, dict[str, Any]] | None = None
        self.task: asyncio.Task[None] | None = None
        self.sent = False
        self.frames = 0  # sets built (tests)
        self.calls: dict[str, float] = {}  # -- I have a response -- the room's pending holds (app/rules/progress.py calls)

    # -- on the worker thread --
    def watch(self, plan: Any, resolved: int) -> None:
        if self.closed:
            return
        started = time.monotonic()
        if started < self.next_at:
            return
        if self.metas is None:
            try:
                self.metas = asyncio.run_coroutine_threadsafe(self._metas(), self.loop).result(timeout=5)
            except Exception:  # noqa: BLE001 - the loop is going away: nothing is shown in between
                self.closed = True
                return
        state = plan.state
        rules = state.rules
        progress = {"resolved": resolved, "by": self.actor,
                    "left": len(state.zones.get("stack", [])) + (len(rules.pending_triggers) if rules is not None else 0)}
        if not self.face_down:
            self.face_down = any(seen and (c := state.cards.get(cid)) is not None and down_public(c)
                                 for cid, seen in (getattr(plan, "moved", None) or {}).items())
        session = self.room.session
        frames: dict[str, dict[str, Any]] = {}
        from app.rules import read_pass

        if not self.face_down and rules is not None and (rules.top_reveals or rules.hideaway) and session.cards is not None:
            # who may see which hidden cards (a revealed library top or hand, a hideaway card) is worked out again only at the end of the
            # action (engine._compile_intent): part way through, the list may still name a source that has since lost the ability. The
            # views are built from a copy brought up to date the same way, never from the list as the action began
            from app.rules import hideaway, permissions
            from app.rules.plan import scratch_copy

            state = scratch_copy(state)
            permissions.refresh_reveals(state, session.cards)
            hideaway.refresh(state)
        # (one read pass for every viewer's view, as a broadcast has: what each derives is worked out once)
        with read_pass.scope(state, session.cards) if session.cards is not None else contextlib.nullcontext():
            for key, (viewer, meta) in self.metas.items():
                message: dict[str, Any] = {"type": "interim", "revision": self.revision, "progress": progress}
                if not self.face_down:
                    message["view"] = session.view(viewer, meta=meta, state=state)
                frames[key] = message
        self.frames += 1
        done = time.monotonic()
        self.next_at = done + max(INTERIM_EVERY, INTERIM_SHARE * (done - started))
        if not self.closed:
            self.loop.call_soon_threadsafe(self._offer, frames)

    # -- on the event loop --
    async def _metas(self) -> dict[str, tuple[str, dict[str, Any]]]:
        return self.hub.interim_metas(self.room)

    def _offer(self, frames: dict[str, dict[str, Any]]) -> None:
        if self.closed:
            return
        self.latest = frames
        if self.task is None:
            self.task = self.loop.create_task(self._drain())

    async def _drain(self) -> None:
        try:
            while self.latest is not None and not self.closed:
                frames, self.latest = self.latest, None
                for conn in list(self.room.connections.values()):
                    if self.closed:
                        return
                    message = frames.get(f"{conn.viewer}:{conn.host}")
                    if message is None:
                        continue  # (connected after this action began: its next update is the action's own)
                    try:
                        await conn.send(message)
                        self.sent = True
                    except Exception:  # noqa: BLE001,S112 - a dead socket: the broadcast after the action drops it
                        continue
        finally:
            self.task = None

    async def close(self) -> None:
        self.closed = True
        self.latest = None
        task = self.task
        if task is not None:
            await task  # (a send under way finishes: a socket is never cut mid-message)


def undo_voters(room: Room, actor: str | None) -> list[str] | None:
    """-- quick undo request -- who approves an undo request from ``actor``: every other seated player still in the game (a LAN
    seat nobody has taken can't answer). None at a hot-seat table, where undo stays direct (app/game/undo_requests.py)."""
    if room.mode == "local" or room.game is None or actor not in room.seats:
        return None
    return [pid for pid in undo_requests.still_in(room.game.state)
            if pid != actor and pid in room.seats and room.seats[pid].token is not None
            and not room.seats[pid].bot]  # (-- LAN bots -- a bot never answers an undo request: it isn't waited for)


def valid_viewer(room: Room, viewer: str) -> bool:
    return viewer in room.seats or viewer in (SPECTATOR, OMNISCIENT)
