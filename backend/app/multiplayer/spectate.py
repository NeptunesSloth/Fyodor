"""Spectator side activities (docs/SPECTATOR_ACTIVITIES_MILESTONE.md) for players who are out and spectators.

Every piece here is outside the live match: it reads only the public (spectator) view or public facts already in every
view (who left the game and how, the recorded result), it never creates a game action, never touches the game's
history, log, revision or saves, and it lives in memory only.

* **Live summary** (``live_summary``): a compact picture of the live game for the practice table's corner (life totals,
  poison, commander damage, whose turn, the stack, the latest public log lines), built from the SPECTATOR view.
* **Predictions** (``Predictions``): fake-point guesses ("who wins", "who is eliminated next") among people who are out or
  spectating. Fixed stakes, a small session balance, picks hidden until the game ends, then revealed and scored. Nothing
  is saved: the balances last as long as the room (the pod's session) and are gone after a restart.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from app.multiplayer.elimination import Pulse

Market = Literal["winner", "next_out"]
MARKETS: tuple[Market, ...] = ("winner", "next_out")
STAKES = (10, 25, 50, 100)
START_BALANCE = 500
LOG_LINES = 6


# --------------------------------------------------------------------------- live summary


def _part_text(part: dict[str, Any]) -> str:
    if "t" in part:
        return str(part["t"])
    if "card" in part:
        return str(part["card"].get("name") or "a card")
    names = [str(g["card"].get("name") or "a card") for g in part.get("group") or []]
    hidden = int(part.get("hidden") or 0)
    if hidden:
        names.append(f"{hidden} hidden card{'s' if hidden != 1 else ''}")
    return ", ".join(names)


def log_text(entry: dict[str, Any]) -> str:
    """One rendered (already per-viewer) log entry as plain text."""
    parts = entry.get("parts") or []
    return "".join(_part_text(p) if isinstance(p, dict) else "".join(_part_text(x) for x in p) for p in parts).strip()


def live_summary(view: dict[str, Any], *, lines: int = LOG_LINES) -> dict[str, Any]:
    """A compact public summary of ``view``, which must be the SPECTATOR view of the live table."""
    rules = view.get("rules") or {}
    lost = rules.get("lost") or {}
    conceded = set(rules.get("conceded") or [])
    names = {p["id"]: p["name"] for p in view["players"]}
    commanders = {c["key"]: c["name"] for p in view["players"] for c in p.get("commanders") or [] if c.get("name")}
    players = []
    for p in view["players"]:
        pid = p["id"]
        out = "left" if p.get("left") else "conceded" if pid in conceded else "lost" if pid in lost else None
        players.append({
            "id": pid, "name": p["name"], "color": p.get("color"), "life": p["life"],
            "poison": int((p.get("resources") or {}).get("poison", 0)), "out": out,
            "hand": p.get("hand_count", 0), "library": p.get("library_count", 0),
            "commander_damage": [{"key": k, "name": commanders.get(k, "Commander"), "damage": n}
                                 for k, n in sorted((p.get("commander_damage") or {}).items()) if n],
        })
    stack = list(view.get("stack") or [])
    top = view["cards"].get(stack[-1]) if stack else None
    top_name = None if top is None else ("A face-down spell" if top.get("hidden") or top.get("face_down") else top.get("name") or "A spell")
    turn = view["turn"]
    decision = rules.get("decision") or None
    log = [t for t in (log_text(e) for e in view.get("log") or []) if t and not t.startswith("—")]
    return {
        "turn": turn["number"], "phase": turn.get("phase"), "active": turn["active_player"],
        "active_name": names.get(turn["active_player"], turn["active_player"]),
        "priority": rules.get("priority"),
        "waiting": decision.get("prompt") if decision else None,
        "players": players,
        "stack": {"count": len(stack), "top": top_name},
        "log": log[-lines:],
    }


# --------------------------------------------------------------------------- predictions


def person_key(token: str) -> str:
    """Who is predicting, by their seat or spectator token (only a hash is kept; tokens are never sent)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


@dataclass
class Pick:
    market: Market
    choice: str  # a game seat still in the game when picked
    stake: int
    after: int = 0  # next_out: how many departures had happened when this was picked
    outcome: Literal["won", "lost", "void"] | None = None


@dataclass
class Predictor:
    name: str
    balance: int = START_BALANCE
    picks: dict[int, dict[str, Pick]] = field(default_factory=dict)  # game number -> market -> pick
    correct: int = 0
    settled: int = 0

    def pending(self, game: int, *, skip: str | None = None) -> int:
        return sum(p.stake for m, p in self.picks.get(game, {}).items() if p.outcome is None and m != skip)


class PredictionError(ValueError):
    pass


@dataclass
class Predictions:
    """Tonight's fake-point predictions at one table (memory only).

    Departures are read from the room's ``Pulse`` (the same public facts as the major-event notices), in batches: the
    players found out at one look went out together. Settling happens once per game, when the recorded result is seen."""

    people: dict[str, Predictor] = field(default_factory=dict)
    game: int | None = None
    departures: list[list[str]] = field(default_factory=list)
    seen_out: set[str] = field(default_factory=set)
    settled: set[int] = field(default_factory=set)
    revealed: dict[int, list[dict[str, Any]]] = field(default_factory=dict)  # game number -> every pick, once scored

    def observe(self, pulse: Pulse, result: dict[str, Any] | None) -> None:
        """Follow the game: who went out since the last look (after ``pulse.observe``), and the result."""
        if pulse.game is None:
            return
        if self.game != pulse.game:
            if self.game is not None and self.game not in self.settled:
                self._settle(self.game, None)  # the game moved on without a result here: its picks are void
            self.game, self.departures, self.seen_out = pulse.game, [], set(pulse.out)
        fresh = sorted(pulse.out - self.seen_out)
        if fresh:
            self.departures.append(fresh)
            self.seen_out |= set(fresh)
        if result is not None and self.game not in self.settled:
            self._settle(self.game, result)

    def place(self, key: str, name: str, *, game: int, market: Market, choice: str, stake: int, candidates: list[str]) -> Pick:
        if stake not in STAKES:
            raise PredictionError(f"Stake {', '.join(map(str, STAKES))} points")
        if choice not in candidates:
            raise PredictionError("Pick a player who is still in the game")
        person = self.people.setdefault(key, Predictor(name=name))
        person.name = name or person.name
        if person.pending(game, skip=market) + stake > person.balance:
            raise PredictionError(f"You have {person.balance - person.pending(game, skip=market)} points left to stake")
        pick = Pick(market=market, choice=choice, stake=stake, after=len(self.departures))
        person.picks.setdefault(game, {})[market] = pick
        return pick

    def withdraw(self, key: str, game: int, market: Market) -> None:
        person = self.people.get(key)
        if person is not None:
            person.picks.get(game, {}).pop(market, None)

    def _settle(self, game: int, result: dict[str, Any] | None) -> None:
        self.settled.add(game)
        winners = set((result or {}).get("winners") or []) if (result or {}).get("result_type") in ("single", "multiple") else None
        rows = []
        for person in self.people.values():
            for pick in person.picks.get(game, {}).values():
                if pick.market == "winner":
                    pick.outcome = "void" if winners is None else "won" if pick.choice in winners else "lost"
                else:
                    later = self.departures[pick.after] if result is not None and pick.after < len(self.departures) else None
                    pick.outcome = "void" if later is None else "won" if pick.choice in later else "lost"
                if pick.outcome != "void":
                    person.settled += 1
                    person.correct += pick.outcome == "won"
                    person.balance += pick.stake if pick.outcome == "won" else -pick.stake
                rows.append({"name": person.name, "market": pick.market, "choice": pick.choice, "stake": pick.stake,
                             "outcome": pick.outcome})
        self.revealed[game] = rows

    def standings(self) -> list[dict[str, Any]]:
        return [{"name": p.name, "balance": p.balance, "correct": p.correct, "settled": p.settled}
                for p in sorted(self.people.values(), key=lambda p: (-p.balance, p.name))]

    def recap(self, game: int, names: Callable[[str], str]) -> dict[str, Any] | None:
        """The reveal for a finished game (public: it is shown to the whole table), None before it is scored or if nobody
        predicted."""
        rows = self.revealed.get(game)
        if not rows:
            return None
        return {"game": game, "picks": [dict(r, choice_name=names(r["choice"])) for r in rows], "standings": self.standings()}

    def mine(self, key: str | None, game: int, names: Callable[[str], str]) -> dict[str, Any]:
        """What one person sees: their own balance and picks (others' picks stay hidden until the reveal)."""
        person = self.people.get(key or "")
        picks = person.picks.get(game, {}) if person else {}
        return {
            "balance": person.balance if person else START_BALANCE,
            "available": (person.balance - person.pending(game)) if person else START_BALANCE,
            "picks": {m: {"choice": p.choice, "choice_name": names(p.choice), "stake": p.stake, "outcome": p.outcome}
                      for m, p in picks.items()},
        }
