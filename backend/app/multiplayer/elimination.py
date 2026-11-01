"""The elimination hub's server side (docs/ELIMINATION_HUB.md).

* **Major public events** ("Bob was eliminated.", "Final two players remain: …", "Alice wins."): what a player
  who is out, practising or just watching should not miss. Each comes from public facts only (who left the
  game, the recorded result) and is announced once per game, never saved or replayed. Clients show the ones
  they haven't seen yet, briefly.
* **Practice tables**: a private, separate game with an eliminated player's own deck while the live game
  goes on. It is its own room and its own ``GameState``; ``PracticeLink`` only says whose it is. It is
  never listed, joined by code, journaled, autosaved or recorded in pod stats, and it reads nothing from
  the live game but that player's own deck.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.game.state import GameState

KEEP_EVENTS = 6  # the newest few: a client only needs the ones it hasn't seen since its last update


def out_players(state: GameState) -> dict[str, str]:
    """Players no longer in the game and how they left it (public: 800.4a, 104.3a)."""
    r = state.rules
    out: dict[str, str] = {}
    for pid in state.seat_order:
        if state.players[pid].left:
            out[pid] = "left"
        elif r is not None and pid in r.conceded:
            out[pid] = "conceded"
        elif r is not None and pid in r.lost:
            out[pid] = "lost"
    return out


def result_text(result: dict[str, Any]) -> str:
    names = list(result.get("winner_names") or [])
    kind = result.get("result_type")
    if kind in ("single", "multiple") and names:
        return f"{' and '.join(names)} {'wins' if len(names) == 1 else 'win'}."
    return "The game is a draw." if kind == "draw" else "The game ended with no result."


@dataclass
class Pulse:
    """The major public events of the room's current game (in memory only)."""

    epoch: str = field(default_factory=lambda: secrets.token_hex(3))  # event ids stay unique across a restart
    game: int | None = None  # the game of the night these events are about
    count: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)
    out: set[str] = field(default_factory=set)
    final_two: bool = False
    result: bool = False

    def public(self) -> list[dict[str, Any]]:
        return [dict(e, players=list(e["players"])) for e in self.events]

    def _add(self, kind: str, text: str, players: list[str]) -> None:
        self.count += 1
        self.events.append({"id": f"{self.epoch}-{self.count}", "game": self.game, "kind": kind, "text": text, "players": players})
        del self.events[:-KEEP_EVENTS]

    def observe(self, state: GameState, game: int, result: dict[str, Any] | None, name: Callable[[str], str]) -> None:
        """Note what changed since the last look. Idempotent: looking twice at the same table adds nothing.

        A new game, or the first look after a restart, starts from what is already true without announcing it.
        Each player's departure, the final two and the result are announced at most once per game (an undo that
        brings a player back doesn't make their next departure news twice)."""
        out = out_players(state)
        live = [pid for pid in state.seat_order if pid not in out]
        if self.game != game:
            self.game, self.events = game, []
            self.out, self.final_two, self.result = set(out), len(live) <= 2, result is not None
            return
        for pid in state.seat_order:
            if pid in out and pid not in self.out:
                self.out.add(pid)
                how = {"lost": "was eliminated", "conceded": "conceded", "left": "left the game"}[out[pid]]
                self._add("out", f"{name(pid)} {how}.", [pid])
        if not self.final_two and len(live) == 2 and result is None:
            self.final_two = True
            self._add("final_two", f"Final two players remain: {name(live[0])} and {name(live[1])}.", list(live))
        if result is not None and not self.result:
            self.result = True
            self._add("result", result_text(result), list(result.get("winners") or []))


@dataclass(frozen=True)
class PracticeLink:
    """Whose practice table a room is: the live game, the seat that owns it there, and which game of the night."""

    live: str
    seat: str
    game: int
    local: bool = False  # the live game is a hot-seat table (the way back names the seat to view)

    def public(self) -> dict[str, Any]:
        return {"of": self.live, "seat": self.seat, "game": self.game, "local": self.local}
