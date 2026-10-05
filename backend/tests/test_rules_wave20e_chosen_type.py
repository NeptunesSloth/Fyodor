"""Wave 20E: "the chosen color" after "Choose a color.". Real Oracle text; every scenario checks the replay and a save and a load.

* 608.2c / 105.1: the color is chosen as the instruction is reached, then "gain protection from the chosen color until end of turn" reads it.
* 702.16b/e: the creatures that gained protection from red can't be targeted by red spells; 611.2c: the set is locked in as it resolves.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import answer, real
from tests.wave9c_kit import build, check, mana, put, to_hand

EXTRA = [
    real("Akroma's Blessing", '{2}{W}', 3, 'Instant', 'Choose a color. Creatures you control gain protection from the chosen color until end of turn.', None, 'W'),
    real('Brave the Elements', '{W}', 1, 'Instant', 'Choose a color. White creatures you control gain protection from the chosen color until end of turn.', None, 'W'),
    real('Probe Soldier', '{1}{W}', 2, 'Creature — Human Soldier', '', ("1", "1"), 'W'),
    real('Probe Burst', '{R}', 1, 'Instant', 'Probe Burst deals 1 damage to any target.', None, 'R'),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", ["Akroma's Blessing", "Brave the Elements"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_protection_from_the_color_that_was_chosen(cards):
    s = build(cards, ["Akroma's Blessing", "Probe Soldier", "Probe Burst"], [])
    soldier = put(s, "Probe Soldier")
    blessing, burst = to_hand(s, "Akroma's Blessing"), to_hand(s, "Probe Burst")
    mana(s, "p1", W=1, C=2, R=1)
    act(s, "p1", type="cast_spell", card_id=blessing.id)
    answer(s, "Red")
    assert not s.state.rules.stack
    with pytest.raises(ActionError):  # (protection from red: a red spell can't target it)
        act(s, "p1", type="cast_spell", card_id=burst.id, targets=[soldier.id])
    act(s, "p1", type="cast_spell", card_id=burst.id, targets=["p2"])  # (the player isn't protected)
    check(s)
