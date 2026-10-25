"""Wave 110H: one-card builds on real Oracle text (every scenario checks replay and a save/load round trip).

* Binding Negotiation: "Otherwise" after an optional choice (608.2c), a face-up exiled card to its owner's graveyard (406.3, 400.3).
"""
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, mana, to_hand

EXTRA = [
    real("Binding Negotiation", "{1}{B}", 2, "Sorcery",
         "Target opponent reveals their hand. You may choose a nonland card from it. If you do, they discard it. Otherwise, you may put a "
         "face-up exiled card they own into their graveyard.", None, "B"),
]
NAMES = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def answer(s, *picks, limit=60):
    """Resolve everything; decisions are answered from ``picks`` in turn, else with their first options."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            pick = picks.pop(0) if picks else None
            ids = pick if isinstance(pick, list) else [pick] if pick else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast(s, name, targets=(), pid="p1", **kw):
    c = to_hand(s, name, pid)
    act(s, pid, type="cast_spell", card_id=c.id, targets=list(targets), **kw)
    return c


def move(s, name, zone, pid="p2"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": zone})
    return s.state.cards[c.id]


@pytest.mark.parametrize("take", [True, False])
def test_binding_negotiation(cards, take):
    """Choosing a nonland card discards it and does nothing else; choosing none puts a face-up exiled card of theirs into their graveyard."""
    s = build(cards, ["Binding Negotiation"], ["Lightning Bolt", "Grizzly Bears"])
    bolt = move(s, "Lightning Bolt", "hand")
    move(s, "Grizzly Bears", "hand")
    exiled = move(s, "Island", "exile")
    mana(s, B=1, C=1)
    cast(s, "Binding Negotiation", ["p2"])
    answer(s, bolt.id if take else [])
    assert s.state.cards[bolt.id].zone == ("p2:graveyard" if take else "p2:hand")
    if not take:
        answer(s, exiled.id)
    assert s.state.cards[exiled.id].zone == ("p2:exile" if take else "p2:graveyard")
    check(s)
