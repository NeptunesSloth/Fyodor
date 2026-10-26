"""Wave 110C: Abaddon the Despoiler: on your turn, a spell you cast from your hand with mana value X or less has cascade (702.85a, 601.2i), X = the life your
opponents have lost this turn (119.3), read as the spell is cast."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import settle, to_hand
from tests.test_rules_effects import mana
from tests.test_rules_wave5b_stack_interaction import build, roundtrip
from tests.wave110c_kit import make_db, real

ABADDON = ("Trample\nMark of Chaos Ascendant — During your turn, spells you cast from your hand with mana value X or less have cascade, where X is the total amount of "
           "life your opponents have lost this turn.")
EXTRA = [real("Abaddon the Despoiler", "{2}{B}{B}", 4, "Legendary Creature — Astartes Warlord", ABADDON, ("4", "4"), "B"),
         real("Three Drop", "{3}", 3, "Creature — Test", "", ("1", "1"), ""),
         real("Four Drop", "{4}", 4, "Creature — Test", "", ("1", "1"), "")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Abaddon the Despoiler")).level == "FULL"


def field(s, name, pid="p1"):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return s.state.cards[c.id]


def cascades(s):
    return sum(1 for e in s.state.rules.stack.values() if e.kind == "trigger" and any(x.get("do") == "cascade" for x in e.effects))


@pytest.mark.parametrize("spell,lost,expected", [("Three Drop", True, 1), ("Four Drop", True, 0), ("Three Drop", False, 0)])
def test_cascade_only_when_mana_value_is_at_most_the_life_opponents_lost(cards, spell, lost, expected):
    s = build(cards, p1=("Abaddon the Despoiler", "Lightning Bolt", "Three Drop", "Four Drop"))
    field(s, "Abaddon the Despoiler")
    if lost:
        mana(s, R=1)
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=["p2"])
        settle(s)
        assert s.state.players["p2"].life == 37
    c = to_hand(s, spell)
    mana(s, C=4)
    act(s, "p1", type="cast_spell", card_id=c.id)
    assert cascades(s) == expected
    roundtrip(s)
