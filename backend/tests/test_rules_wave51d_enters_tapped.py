"""Wave 51D: "You may play target … card from your graveyard this turn. If you do, it enters tapped." (CR 2026-09-25), real Oracle text (tests/fixtures/wave51d_cards.json, from
data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 614.1d / 305.1 / 601.2: Jorn, God of Winter (Kaldring, the Rimestaff) - the rider is for the land played or the permanent spell cast with the permission; a card played
  from the hand some other way enters as it normally does.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, next_turn, settle
from tests.wave9c_kit import build, card_named, check, mana, put, reloaded, to_hand, zone_of
from tests.wave51d_kit import open_repo

JORN = "Jorn, God of Winter // Kaldring, the Rimestaff"

@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


def test_the_card_is_full(cards):
    assert coverage.of_card_data(cards.resolve(JORN)).level == "FULL"


def kaldring(cards, dead):
    s = build(cards, [JORN, *dead], forests=30)
    k = put(s, JORN)
    act(s, "p1", type="set_face", card_id=k.id, face=1)  # Kaldring, the Rimestaff (a permanent that has been there since the turn began)
    for name in dead:
        c = put(s, name)
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    next_turn(s)
    return s, k


def test_a_snow_land_played_with_kaldring_enters_tapped(cards):
    s, k = kaldring(cards, ["Snow-Covered Forest"])
    land = card_named(s, "Snow-Covered Forest")
    activate(s, "p1", k, targets=[land.id])
    settle(s)
    act(s, "p1", type="play_land", card_id=land.id)
    assert zone_of(s, "Snow-Covered Forest") == "p1:battlefield" and s.state.cards[land.id].tapped
    check(s)
    assert reloaded(s).state.cards[land.id].tapped


def test_a_snow_creature_cast_with_kaldring_enters_tapped(cards):
    s, k = kaldring(cards, ["Boreal Druid"])
    druid = card_named(s, "Boreal Druid")
    activate(s, "p1", k, targets=[druid.id])
    settle(s)
    mana(s, "p1", G=2)
    act(s, "p1", type="cast_spell", card_id=druid.id)
    settle(s)
    assert zone_of(s, "Boreal Druid") == "p1:battlefield" and s.state.cards[druid.id].tapped
    check(s)


def test_kaldring_cannot_pick_a_card_that_is_not_snow(cards):
    s, k = kaldring(cards, ["Grizzly Bears"])
    with pytest.raises(ActionError):
        activate(s, "p1", k, targets=[card_named(s, "Grizzly Bears").id])
    check(s)


def test_a_snow_land_played_from_the_hand_enters_untapped(cards):
    s, k = kaldring(cards, ["Snow-Covered Forest"])
    land = to_hand(s, "Snow-Covered Forest")
    act(s, "p1", type="play_land", card_id=land.id)
    assert zone_of(s, "Snow-Covered Forest") == "p1:battlefield" and not s.state.cards[land.id].tapped
    check(s)
