"""Wave 110I (second session): real Oracle text; every scenario checks the replay and a save and a load.

* The Moment: "phases out until The Moment leaves the battlefield" (610.3, 702.26a), untapped first, not tapped as it returns.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave110c_kit import answer, build, cast, check, make_db, mana, put, zone

EXTRA = [
    real("The Moment", "{1}{W}{U}", 3, "Legendary Artifact",
         "At the beginning of your upkeep, put a time counter on The Moment.\n{2}, {T}: Untap target creature you control. It phases out until The Moment leaves the battlefield.\n{3}, {T}: Destroy each nonland permanent with mana value less than or equal to the number of time counters on The Moment. Then sacrifice The Moment. Activate only as a sorcery.",
         None, "WU"),
    real("Naturalize", "{1}{G}", 2, "Instant", "Destroy target artifact or enchantment.", None, "G"),
]
NAMES = ["The Moment"]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_the_moment_phases_out_untapped_until_it_leaves(cards):
    s = build(cards, ["The Moment", "Naturalize", "Grizzly Bears"], [])
    moment, bear = put(s, "The Moment"), put(s, "Grizzly Bears")
    act(s, "p1", type="tap", card_ids=[bear.id])
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=moment.id, ability=1, targets=[bear.id])
    answer(s)
    assert zone(s, bear) == "p1:phased" and not s.state.cards[bear.id].tapped
    check(s)
    mana(s, G=1, C=1)
    cast(s, "Naturalize", [moment.id])
    answer(s)
    assert zone(s, bear) == "p1:battlefield" and not s.state.cards[bear.id].tapped
    check(s)
