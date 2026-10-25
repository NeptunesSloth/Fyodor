"""Wave 110A: promotions on real Oracle text (replay + save/load via tests/wave9c_kit.check).

* 601.2c, 608.2b: "Choose any number of target creatures with equal toughness. Destroy the chosen creatures." (V.A.T.S.).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave100n_multi import EXTRA as _BASE
from tests.test_rules_wave100n_multi import answer, card_db, cast  # noqa: F401  (fixture DB with EXTRA)
from tests.wave9c_kit import build, check, mana, put, zone_of

EXTRA = [
    real("V.A.T.S.", "{2}{B}{B}", 4, "Sorcery", "Choose any number of target creatures with equal toughness. Destroy the chosen creatures.", None, "B"),
    real("Test Two 110A", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
    real("Test Twin 110A", "{1}{G}", 2, "Creature — Cat", "", ("1", "2"), "G"),
    real("Test Three 110A", "{2}{G}", 3, "Creature — Ox", "", ("3", "3"), "G"),
]
_BASE.extend(EXTRA)
NAMES = ["V.A.T.S."]


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_vats_destroys_equal_toughness_only(cards):
    s = build(cards, ["V.A.T.S.", "Test Two 110A", "Test Twin 110A"], ["Test Three 110A"])
    a, b = put(s, "Test Two 110A"), put(s, "Test Twin 110A")
    put(s, "Test Three 110A", "p2")
    mana(s, B=2, C=2)
    cast(s, "V.A.T.S.", [a.id, b.id], target_counts=[2])
    answer(s)
    assert zone_of(s, "Test Two 110A") == "p1:graveyard" and zone_of(s, "Test Twin 110A") == "p1:graveyard"
    assert zone_of(s, "Test Three 110A", "p2") == "p2:battlefield"
    check(s)


def test_vats_refuses_unequal_toughness(cards):
    s = build(cards, ["V.A.T.S.", "Test Two 110A"], ["Test Three 110A"])
    a, c = put(s, "Test Two 110A"), put(s, "Test Three 110A", "p2")
    mana(s, B=2, C=2)
    with pytest.raises(ActionError, match="equal toughness"):
        cast(s, "V.A.T.S.", [a.id, c.id], target_counts=[2])
