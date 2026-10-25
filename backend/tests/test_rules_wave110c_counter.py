"""Wave 110C counter outcomes: Desertion (608.2c, 701.6a: the countered artifact or creature spell enters under the counterer's control)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110c_kit import answer, build, cast, check, make_db, mana, real, to_hand, zone

EXTRA = [real("Desertion", "{3}{U}{U}", 5, "Instant",
              "Counter target spell. If an artifact or creature spell is countered this way, put that card onto the battlefield under your control instead of into its owner's graveyard.", None, "U")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Desertion")).level == "FULL"


@pytest.mark.parametrize("name,dest", [("Grizzly Bears", "p2:battlefield"), ("Lightning Bolt", "p1:graveyard")])
def test_desertion_steals_countered_creature_spell_only(cards, name, dest):
    s = build(cards, [name], ["Desertion"])
    mana(s, "p1", R=1, G=1, C=1)
    mana(s, "p2", U=2, C=3)
    des = to_hand(s, "Desertion", "p2")
    victim = cast(s, name, ["p2"] if name == "Lightning Bolt" else [])
    act(s, "p2", type="cast_spell", card_id=des.id, targets=[victim.id])
    answer(s)
    assert zone(s, victim) == dest
    check(s)
