"""Shared helpers of the pod-deck audit tests for Ian Malcolm, Kiora and Adrix and Nev (tests/test_rules_pod_{ian,kiora,adrix}.py).

A two-player table (Alice p1, Bob p2) with rules automation on, built from the small fixture database plus each file's real Oracle text.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from typing import Any

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules.plan import Plan
from tests.game_helpers import act, deck, enable


def table(cards, mine: Iterable[str] = (), theirs: Iterable[str] = (), *, commander: str = "Krenko, Mob Boss",
          lands: tuple[str, int] = ("Forest", 10), their_lands: tuple[str, int] = ("Island", 10)) -> GameSession:
    """Alice (``commander``, ``mine`` and basic lands) against Bob (Atraxa), unshuffled, in Alice's first main phase."""
    alice = deck(cards, commander, [*((1, n) for n in mine), (lands[1], lands[0])])
    bob = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in theirs), (their_lands[1], their_lands[0])])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def card(s, name: str, pid: str = "p1"):
    """The first card of that name the player owns (wherever it is)."""
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def put(s, name: str, pid: str = "p1"):
    c = card(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return s.state.cards[c.id]


def to_hand(s, name: str, pid: str = "p1"):
    c = card(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "hand"})
    return c


def on_top(s, *names: str, pid: str = "p1") -> None:
    """The named cards on top of the library, the first named on top."""
    for name in reversed(names):
        act(s, pid, type="move", card_ids=[card(s, name, pid).id], to={"player": pid, "zone": "library"}, position="top")


def mana(s, pid: str = "p1", **m: int) -> None:
    act(s, pid, type="add_mana", player=pid, mana=m)


def hold(s, pid: str = "p1") -> None:
    act(s, pid, type="set_prefs", hold_priority=True)


Pick = str | Callable[[Any], list[str] | None]


def settle(s, *picks: Pick, limit: int = 80, stop_at: str | None = None) -> list[str]:
    """Resolve everything. Each decision is answered with the first pick that fits (a label prefix, or a function of the decision giving
    option ids), else its first options; an order takes the listed order; no one attacks or blocks. Returns the prompts asked. Stops
    (unanswered) at a decision whose prompt starts with ``stop_at``."""
    todo, asked = list(picks), []
    for _ in range(limit):
        if s.state.rules.winner:
            return asked
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
            continue
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
            continue
        if d is not None and stop_at is not None and d.prompt.startswith(stop_at):
            return asked
        if d is not None:
            asked.append(d.prompt)
            chosen: list[str] | None = [o.id for o in d.options] if d.kind == "order" else None
            for i, p in enumerate(todo if chosen is None else []):
                got = p(d) if callable(p) else [o.id for o in d.options if (o.label or "").startswith(p)][: max(1, d.max_choices or 1)]
                if got is not None and (got or callable(p)):
                    chosen = got
                    todo.pop(i)
                    break
            if chosen is None:
                chosen = [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=chosen)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return asked
    raise AssertionError("never settled")


def cast(s, name: str, *picks: Pick, pid: str = "p1", **kw: Any) -> list[str]:
    c = card(s, name, pid)
    if not c.zone.endswith((":hand", ":exile", ":command")):
        c = to_hand(s, name, pid)
    act(s, pid, type="cast_spell", card_id=c.id, **kw)
    return settle(s, *picks)


def until(s, active: str, phase: str, *picks: Pick, limit: int = 60) -> None:
    """Pass priority until it is ``active``'s ``phase`` with an empty stack (or the game is over)."""
    for _ in range(limit):
        settle(s, *picks)
        if s.state.rules.winner or (s.state.turn.active_player == active and s.state.turn.phase == phase and not s.state.zones.get("stack")):
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"never reached {active} {phase}")


def ch(s, c, pid: str = "p1"):
    return Plan(s.state, pid, s.cards, None).ch(s.state.cards[c.id])


def field(s, pid: str = "p1") -> Counter[str]:
    """Names (as they are now, after copy effects) of the permanents the player controls."""
    return Counter(ch(s, s.state.cards[i], pid).name or "" for i in s.state.zones[f"{pid}:battlefield"])


def named(s, name: str, pid: str = "p1") -> list[Any]:
    return [s.state.cards[i] for i in s.state.zones[f"{pid}:battlefield"] if ch(s, s.state.cards[i], pid).name == name]


def zone_names(s, pid: str, zone: str) -> list[str]:
    return sorted(s.state.cards[i].name for i in s.state.zones[f"{pid}:{zone}"])
