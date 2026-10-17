"""Wave 45A: "Round up each time" / "Round down each time" (107.1a), real Oracle text (tests/fixtures/wave45a_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* Peer into the Abyss [1293]: "Target player draws cards equal to half the number of cards in their library and loses half their life. Round up each time." - the
  cards drawn and the life lost are rounded up, not what remains (ruling 2020-06-23); a library's size is public.
* Fraying Omnipotence [8843] (up), Pox Plague [9916] (down): "Each player loses half their life, then discards half the cards in their hand, then sacrifices half the
  creatures / permanents they control of their choice." - each half rounded the way the last sentence says.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import settle
from tests.wave9c_kit import build, check, mana, put, to_hand
from tests.wave45a_kit import cast, life, open_cards


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


@pytest.mark.parametrize("name", ["Peer into the Abyss", "Fraying Omnipotence", "Pox Plague"])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def creatures(s, pid):
    return [c for c in s.state.zones[f"{pid}:battlefield"] if s.state.cards[c].name in ("Hill Giant", "Grizzly Bears", "Goblin Piker")]


def test_peer_into_the_abyss_draws_half_the_library_and_loses_half_the_life_both_rounded_up(cards):
    s = build(cards, ["Peer into the Abyss"], [], islands=10)
    to_hand(s, "Peer into the Abyss")
    act(s, "p2", type="life", delta=-1)  # Bob: 39 (an odd total: the half rounds up to 20)
    library, hand = len(s.state.zones["p2:library"]), len(s.state.zones["p2:hand"])
    mana(s, B=3, C=4)
    cast(s, "Peer into the Abyss", targets=["p2"])
    assert len(s.state.zones["p2:hand"]) == hand + (library + 1) // 2
    assert life(s, "p2") == 39 - 20
    check(s)


def test_fraying_omnipotence_halves_life_hand_and_creatures_rounding_up(cards):
    s = build(cards, ["Fraying Omnipotence", "Hill Giant", "Grizzly Bears", "Goblin Piker"], [])
    for name in ("Hill Giant", "Grizzly Bears"):
        put(s, name)
    to_hand(s, "Goblin Piker")
    to_hand(s, "Fraying Omnipotence")
    act(s, "p1", type="life", delta=-1)  # Alice: 39
    hand_p2 = len(s.state.zones["p2:hand"])
    mana(s, B=2, C=3)
    cast(s, "Fraying Omnipotence")
    settle(s)
    assert life(s, "p1") == 39 - 20 and life(s, "p2") == 40 - 20
    assert len(s.state.zones["p1:hand"]) == 0  # one card left after the cast: half of one, rounded up, is one
    assert len(s.state.zones["p2:hand"]) == hand_p2 - (hand_p2 + 1) // 2
    assert len(creatures(s, "p1")) == 1  # half of two creatures
    check(s)


def test_pox_plague_rounds_every_half_down(cards):
    s = build(cards, ["Pox Plague", "Hill Giant", "Grizzly Bears", "Goblin Piker"], [])
    for name in ("Hill Giant", "Grizzly Bears", "Goblin Piker"):
        put(s, name)
    to_hand(s, "Pox Plague")
    act(s, "p1", type="life", delta=-1)  # Alice: 39
    mana(s, B=5)
    cast(s, "Pox Plague")
    settle(s)
    assert life(s, "p1") == 39 - 19 and life(s, "p2") == 40 - 20  # 39: half is 19.5, rounded down
    assert len(creatures(s, "p1")) == 2  # half of three permanents, rounded down: one sacrificed
    check(s)
