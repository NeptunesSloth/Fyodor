"""Bringing my decks to another computer's table (docs/LAN_PLAY.md, "Finding a game").

A player who joins a table found under *Games on your network* runs their own Fyodor, with their own deck library. Their server
sends that library to the host's server (``POST /api/lan/handoff``), which keeps it **in memory only** behind a random one-time
token for ``TTL`` seconds. The join link carries the token; joining attaches the library to that seat alone, and the seat's
*Choose deck* lists it. It is never saved, journaled or logged, and it is dropped when the seat leaves or the game starts (the
chosen deck stays, as any brought deck does).
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.multiplayer.hub import Room

TTL = 600  # seconds a handoff waits for its join
MAX_DECKS = 60
MAX_BYTES = 1_000_000  # one library, as sent
MAX_PENDING = 16  # libraries waiting for their join (the oldest go first)
MAX_ATTACHED = 64  # libraries held for seats
OFFERS_PER_MINUTE = 10  # per sending address


class HandoffRefused(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class BroughtDeck:
    name: str
    commanders: list[str]
    text: str  # the list in the form the lobby's paste and import accept


@dataclass
class Library:
    source: str  # the sending computer's name ("From DANA-PC")
    decks: list[BroughtDeck]
    created: float = 0.0


@dataclass
class Handoffs:
    clock: Callable[[], float] = time.monotonic
    pending: dict[str, Library] = field(default_factory=dict)
    attached: dict[tuple[str, str], Library] = field(default_factory=dict)  # (room id, seat token) -> library
    offers: dict[str, list[float]] = field(default_factory=dict)

    def __repr__(self) -> str:  # never print tokens or libraries
        return f"Handoffs(pending={len(self.pending)}, attached={len(self.attached)})"

    def _expire(self, now: float) -> None:
        for token in [t for t, lib in self.pending.items() if now - lib.created > TTL]:
            del self.pending[token]

    def offer(self, library: Library, sender: str) -> str:
        """Hold ``library`` for one join; returns its token. Refused (429) when one address sends too many."""
        now = self.clock()
        self._expire(now)
        recent = [t for t in self.offers.get(sender, ()) if now - t < 60]
        if len(recent) >= OFFERS_PER_MINUTE:
            raise HandoffRefused(429, "Too many deck libraries sent from this computer; wait a minute")
        self.offers = {k: v for k, v in self.offers.items() if v and now - v[-1] < 60}
        self.offers[sender] = [*recent, now]
        while len(self.pending) >= MAX_PENDING:
            self.pending.pop(next(iter(self.pending)))
        library.created = now
        token = secrets.token_urlsafe(24)
        self.pending[token] = library
        return token

    def take(self, token: str | None) -> Library | None:
        """The library behind ``token``, once (it is gone afterwards), unless it has expired."""
        self._expire(self.clock())
        return self.pending.pop(token, None) if token else None

    def attach(self, room_id: str, seat_token: str, library: Library) -> None:
        while len(self.attached) >= MAX_ATTACHED:
            self.attached.pop(next(iter(self.attached)))
        self.attached[(room_id, seat_token)] = library

    def brought(self, room: Room, seat_token: str) -> Library | None:
        """The library this seat brought, while it still holds the seat and the game hasn't started."""
        key = (room.id, seat_token)
        library = self.attached.get(key)
        if library is None:
            return None
        if room.started or room.seat_for_token(seat_token) not in room.seats:
            del self.attached[key]
            return None
        return library

    def drop_room(self, room_id: str) -> None:
        """The game started (or the table closed): every library brought to it goes."""
        for key in [k for k in self.attached if k[0] == room_id]:
            del self.attached[key]

    def drop_seat(self, room_id: str, seat_token: str | None) -> None:
        if seat_token:
            self.attached.pop((room_id, seat_token), None)
