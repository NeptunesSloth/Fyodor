"""Game night: several games with the same pod at one room (docs/GAME_NIGHT_FLOW.md).

The room outlives each game. ``Night`` holds what carries over (who brought which deck, the last
turn order and result) and the post-game decisions (an agreed ending, the rematch vote). Nothing
match-local carries into the next game: a rematch builds a brand-new game from the same decks.

Turn order follows the pod rule: game 1 and every game after a draw open with server-side d20
rolls (ties reroll among the tied players only); otherwise the previous winner goes last and the
others keep their relative order. Clients never roll or decide anything.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from app.game.factory import PlayerSetup
from app.multiplayer.lobby import LobbySeatInfo

OrderSource = Literal["d20", "winner_last", "host"]
Choice = Literal["rematch", "lobby"]
ResultType = Literal["single", "multiple", "draw", "no_result"]


def d20() -> int:
    return secrets.randbelow(20) + 1


def roll_order(keys: list[str], roll: Callable[[], int] = d20) -> tuple[list[str], list[dict[str, int]]]:
    """Order ``keys`` by d20, highest first. Ties reroll among the tied players only, as often as needed.

    Returns the order and every round of rolls (round 0 is everyone; later rounds are tie-breaks).
    """
    rounds: list[dict[str, int]] = []

    def settle(group: list[str]) -> list[str]:
        if len(group) <= 1:
            return list(group)
        rolls = {k: roll() for k in group}
        rounds.append(rolls)
        out: list[str] = []
        for value in sorted(set(rolls.values()), reverse=True):
            out += settle([k for k in group if rolls[k] == value])
        return out

    return settle(list(keys)), rounds


def winner_last(order: list[str], winner: str) -> list[str]:
    """The previous winner goes last; everyone else keeps their relative order."""
    if winner not in order:
        return list(order)
    return [k for k in order if k != winner] + [winner]


@dataclass
class Proposal:
    """A player's proposal to end the game now with a given result; every remaining player must agree."""

    by: str
    result_type: ResultType
    winners: list[str]
    agreed: set[str] = field(default_factory=set)

    def public(self, names: Callable[[str], str]) -> dict[str, Any]:
        return {"by": self.by, "by_name": names(self.by), "result_type": self.result_type, "winners": list(self.winners),
                "winner_names": [names(w) for w in self.winners], "agreed": sorted(self.agreed)}


@dataclass
class Night:
    number: int = 1  # the game number within this pod session
    order_source: OrderSource = "host"
    rolls: list[dict[str, int]] = field(default_factory=list)  # d20 rounds for this game, by game seat
    previous_winner: str | None = None  # game seat of last game's winner (who now goes last)
    # What each seat brought to this game (game seat -> setup), for a same-decks rematch.
    setups: dict[str, PlayerSetup] = field(default_factory=dict)
    # Lobby seat info (deck, colour, name) per game seat, so returning to the lobby keeps each deck selected.
    infos: dict[str, LobbySeatInfo] = field(default_factory=dict)
    proposal: Proposal | None = None
    # After a recorded result: the outcome and each seat's choice.
    result: dict[str, Any] | None = None
    votes: dict[str, Choice] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)  # one entry per finished game
    # Seat token (or, at a hot-seat table, game seat) of the last game's single winner; never sent to clients.
    last_winner_key: str | None = None

    def result_key(self, room_id: str) -> str:
        """The pod-stats game id of the current game (game 1 keeps the room id; later games add #n)."""
        return room_id if self.number == 1 else f"{room_id}#{self.number}"

    @staticmethod
    def plan(seats: list[str], winner: str | None, roll: Callable[[], int] = d20) -> tuple[list[str], OrderSource, list[dict[str, int]]]:
        """Turn order for the next game over ``seats``: the previous single winner goes last, else d20."""
        if winner is not None and winner in seats:
            return winner_last(seats, winner), "winner_last", []
        order, rounds = roll_order(seats, roll)
        return order, "d20", rounds

    def remap(self, mapping: dict[str, str]) -> None:
        """Seats were renumbered for a new game (old seat -> new seat)."""
        self.setups = {mapping[k]: v for k, v in self.setups.items() if k in mapping}
        self.infos = {mapping[k]: v for k, v in self.infos.items() if k in mapping}
        self.rolls = [{mapping[k]: v for k, v in r.items() if k in mapping} for r in self.rolls]
        self.previous_winner = mapping.get(self.previous_winner or "")

    def public(self, names: Callable[[str], str]) -> dict[str, Any]:
        """Everything here is public: rolls, order, proposals, the result and the votes."""
        return {
            "number": self.number,
            "order_source": self.order_source,
            "rolls": [dict(r) for r in self.rolls],
            "previous_winner": self.previous_winner,
            "proposal": self.proposal.public(names) if self.proposal else None,
            "result": self.result,
            "votes": dict(self.votes),
            "history": [dict(h) for h in self.history],
        }

    def meta(self) -> dict[str, Any]:
        """Crash-recovery record (setups and lobby infos are rebuilt by the host if lost)."""
        return {"number": self.number, "order_source": self.order_source, "rolls": self.rolls,
                "previous_winner": self.previous_winner, "result": self.result, "votes": dict(self.votes),
                "history": self.history, "last_winner_key": self.last_winner_key}

    @classmethod
    def from_meta(cls, meta: dict[str, Any] | None) -> Night:
        night = cls()
        if not meta:
            return night
        night.number = int(meta.get("number") or 1)
        night.order_source = meta.get("order_source") or "host"
        night.rolls = list(meta.get("rolls") or [])
        night.previous_winner = meta.get("previous_winner")
        night.result = meta.get("result")
        night.votes = dict(meta.get("votes") or {})
        night.history = list(meta.get("history") or [])
        night.last_winner_key = meta.get("last_winner_key")
        return night
