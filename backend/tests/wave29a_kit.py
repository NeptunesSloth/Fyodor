"""Rich tables for the wave 29A hint checks (real Oracle text, tests/fixtures/wave29a_hints_cards.json, from data/cards.sqlite).

Nothing here depends on how ``view.hints`` is computed: the same builders produce the golden snapshot at the base commit
(tests/fixtures/wave29a_hints_golden.json) and the boards the speed-up is compared against. ``snapshot`` is the player's whole rules view
with every random card id replaced by a stable label, so two runs of a board give the same text."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules.view import rules_view
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import settle
from tests.test_rules_effects import mana

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave29a_hints_cards.json").read_text("utf-8"))
EXTRA = [card(c["name"], set_code="t29a", number=f"H{i:03d}", **{k: v for k, v in c.items() if k != "name"}) for i, c in enumerate(DATA)]


def all_cards() -> list[dict[str, Any]]:
    return [*fixture_cards(), *EXTRA]


def table(cards, mine: dict[str, list[Any]] | None = None, theirs: dict[str, list[Any]] | None = None, *, active: str = "p1") -> GameSession:
    """Alice (p1, Krenko) and Bob (p2, Atraxa) with rules automation on. ``mine`` / ``theirs``: zone -> cards (a name, or (name, how many))
    put there from the library before play; ``active``: whose main phase it is, and who has priority."""
    zones: dict[str, dict[str, list[Any]]] = {"p1": mine or {}, "p2": theirs or {}}
    decks = []
    for pid, commander, filler in (("p1", "Krenko, Mob Boss", "Forest"), ("p2", "Atraxa, Praetors' Voice", "Island")):
        counts: dict[str, int] = {}
        for items in zones[pid].values():
            for it in items:
                name, n = (it, 1) if isinstance(it, str) else it
                counts[name] = counts.get(name, 0) + n
        decks.append(deck(cards, commander, [*((n, name) for name, n in counts.items()), (12, filler)]))
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=decks[0]), PlayerSetup("Bob", cards=decks[1])], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's first main phase
    for pid in ("p1", "p2"):
        for zone, items in zones[pid].items():
            for it in items:
                name, n = (it, 1) if isinstance(it, str) else it
                for _ in range(n):
                    put(s, name, zone, pid)
    if active == "p2":
        for _ in range(60):
            if s.state.turn.active_player == "p2" and s.state.turn.phase == "main1" and s.state.rules.decision is None:
                break
            d = s.state.rules.decision
            if d is not None and d.kind == "declare_attackers":
                act(s, d.player, type="declare_attackers", attackers=[])
            elif d is not None and d.kind == "declare_blockers":
                act(s, d.player, type="declare_blockers", blocks=[])
            elif d is not None:
                act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
            else:
                act(s, s.state.rules.priority, type="pass_priority")
    return s


def put(s, name: str, zone: str, pid: str = "p1") -> Any:
    """Move the first copy of ``name`` still in the library of ``pid`` to ``zone`` ("battlefield", "hand", "graveyard", "exile", "command",
    "library" = the top of it)."""
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library")
    payload: dict[str, Any] = {"type": "move", "card_ids": [c.id], "to": {"player": pid, "zone": zone}}
    if zone == "library":
        payload["position"] = "top"
    act(s, pid, **payload)
    settle(s)
    return s.state.cards[c.id]


def token(s, pid: str, name: str, pt: str = "2/2", text: str = "", type_line: str = "Token Creature — Test") -> Any:
    p, t = pt.split("/")
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": type_line, "power": p, "toughness": t, "text": text})
    return next(c for c in reversed(list(s.state.cards.values())) if c.name == name and c.owner == pid)


def cast(s, name: str, pid: str = "p1", **kw: Any) -> None:
    """Cast the first copy of ``name`` in the hand of ``pid`` and keep priority (so it stays on the stack)."""
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:hand")
    act(s, pid, type="set_prefs", hold_priority=True)
    act(s, pid, type="cast_spell", card_id=c.id, **kw)


def lands(s, pid: str = "p1", **colors: int) -> None:
    mana(s, pid, **colors)


_ID = re.compile(r"\b[0-9a-f]{12}\b")


def snapshot(s) -> dict[str, Any]:
    """Every player's rules view as JSON-able data, card ids replaced by ``owner/name/n`` (n: nth card of that name, in table order)."""
    seen: dict[tuple[str, str], int] = {}
    label: dict[str, str] = {}
    for cid, c in s.state.cards.items():
        n = seen[(c.owner, c.name)] = seen.get((c.owner, c.name), 0) + 1
        label[cid] = f"{c.owner}/{c.name}/{n}"
    out: dict[str, Any] = {}
    for pid in s.state.players:
        text = json.dumps(rules_view(s.state, pid, s.cards), sort_keys=True, ensure_ascii=False, default=str)
        out[pid] = json.loads(_ID.sub(lambda m: label.get(m.group(0), m.group(0)), text))
        out[pid].pop("repeatable", None)  # (REPEAT's list of the player's own actions came later: neither a hint nor a stat)
        if out[pid].get("decision"):
            out[pid]["decision"]["id"] = "<decision>"  # (random per decision)
    return out
