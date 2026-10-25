"""Wave 110B session 10: single cards read from an exact wording (real Oracle text in tests/fixtures/wave110b_cards.json).

* Equal Treatment: 614.1a, 611.2a "any source would deal 1 or more damage ... this turn, 2 instead": 3 becomes 2, 1 becomes 2 (Flameblade ping), then draw.
* Flameblade Angel: 120.3 / 603.2 damage from an opponent's source to you or to a permanent you control triggers once; 603.7-free "may" 1 damage to that source's controller.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110b_kit import build, cast, check, drive, mana, put, repository, to_hand


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


@pytest.mark.parametrize("name", ["Flameblade Angel", "Equal Treatment"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("aim, pings", [("player", 1), ("bears", 1), ("p2bears", 0)])
def test_flameblade_angel_pings_the_controller_of_a_source_that_hit_you_or_yours(cards, aim, pings):
    s = build(cards, ["Flameblade Angel", "Grizzly Bears", "Lightning Bolt"], ["Lightning Bolt", "Grizzly Bears"])
    put(s, "Flameblade Angel")
    bears = put(s, "Grizzly Bears")
    p2bears = put(s, "Grizzly Bears", "p2")
    act(s, "p2", type="set_prefs", response="on")
    act(s, "p1", type="set_prefs", response="on")
    mana(s, "p2", R=1)
    s.state.rules.priority = "p2"
    target = {"player": "p1", "bears": bears.id, "p2bears": p2bears.id}[aim]
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Lightning Bolt", "p2").id, targets=[target])
    drive(s)
    assert s.state.players["p2"].life == 40 - pings
    check(s)


def test_equal_treatment_sets_every_damage_to_2_this_turn(cards):
    s = build(cards, ["Equal Treatment", "Flameblade Angel", "Lightning Bolt", "Forest"], ["Lightning Bolt"])
    put(s, "Flameblade Angel")
    mana(s, "p1", W=1, C=1)
    hand = len(s.state.zones["p1:hand"])
    cast(s, "Equal Treatment")
    assert len(s.state.zones["p1:hand"]) == hand + 1  # drew a card (the spell left the hand, the draw came in)  # noqa: E501
    act(s, "p2", type="set_prefs", response="on")
    act(s, "p1", type="set_prefs", response="on")
    mana(s, "p2", R=1)
    s.state.rules.priority = "p2"
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Lightning Bolt", "p2").id, targets=["p1"])
    drive(s)
    assert s.state.players["p1"].life == 38  # 3 -> 2
    assert s.state.players["p2"].life == 38  # Angel's 1 -> 2
    check(s)
