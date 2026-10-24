"""Shared helpers of the wave 100E tests (app/rules/xdamage100e.py): the real cards of tests/fixtures/wave100e_xdamage_cards.json (from
data/cards.sqlite) plus a few probes, and table helpers."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules.casting import castable
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import put

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave100e_xdamage_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w100e", number=f"E{i:03d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN] + [
    real("Probe Hamster", "{2}{R}", 3, "Creature — Hamster", "", ("3", "3"), "R"),
    real("Probe Ember", "{R}", 1, "Enchantment", "", None, "R"),
    real("Probe Army", "{1}{B}", 2, "Creature — Zombie Army", "", ("1", "1"), "B"),
    real("Probe Wall", "{3}", 3, "Creature — Wall", "", ("0", "6")),
    real("Probe Faerie", "{U}", 1, "Creature — Faerie", "Flying", ("1", "1"), "U"),
    real("Probe Plains", "", 0, "Basic Land — Plains", "({T}: Add {W}.)", None),
]


def repo(settings: Any) -> Iterator[CardRepository]:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    r = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield r
    r.close()


def answer(s, *prefer, limit=60):
    """Resolve everything; a choice is answered with ``prefer`` (when offered) or its first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            want = [o for o in prefer if o in ids]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=want if len(want) >= max(1, d.min_choices) else ids[: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def pick(s, kind, *ids, limit=20):
    """Pass priority until a decision of this kind is pending, then answer it with exactly these options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            assert d.kind == kind, (d.kind, d.prompt)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=list(ids))
            return d
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no decision came up")


def loyal(s, name, pid="p1", loyalty=10, face=None):
    """A planeswalker on the battlefield with loyalty (an enters trigger's "may": declined)."""
    c = put(s, name, pid)
    answer(s, "no")
    if face is not None:
        act(s, pid, type="set_face", card_id=c.id, face=face)
    act(s, pid, type="counter", card_ids=[c.id], kind="loyalty", delta=loyalty)
    return c


def full_control(s):
    """Nothing resolves on its own: a player can act while something waits on the stack."""
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", full_control=True)


def hand(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:hand", []))


def library(s, pid):
    return list(s.state.zones.get(f"{pid}:library", []))


def chars(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def zone_of(s, c):
    return s.state.cards[c.id].zone


def can_cast(s, pid, c):
    return castable(s.state, pid, s.state.cards[c.id], s.cards, check_priority=False)


def tokens(s, name, pid):
    return [c for c in s.state.cards.values() if c.name == name and c.zone == f"{pid}:battlefield"]


def to_phase(s, phase, turn=None, limit=300):
    """Pass priority (no attackers, no blockers) until ``phase`` of the turn ``turn`` turns from now is reached."""
    turn = None if turn is None else s.state.turn.number + turn
    for _ in range(limit):
        d = s.state.rules.decision
        if s.state.turn.phase == phase and turn in (None, s.state.turn.number):
            return
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"never reached {phase} of turn {turn}")


def set_hand(s, pid, n):
    """Exactly n cards in that player's hand (from the top of their library, or the extra ones to the graveyard)."""
    for cid in list(s.state.zones.get(f"{pid}:hand", []))[n:]:
        act(s, pid, type="move", card_ids=[cid], to={"player": pid, "zone": "graveyard"})
    for cid in library(s, pid)[: max(0, n - hand(s, pid))]:
        act(s, pid, type="move", card_ids=[cid], to={"player": pid, "zone": "hand"})
    assert hand(s, pid) == n
