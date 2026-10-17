"""Wave 45A: "base power and toughness X/X, where X is ..." (CR 2026-09-25), real Oracle text (tests/fixtures/wave45a_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 613.4b, 611.3a: Aettir and Priwen [2745] - "Equipped creature has base power and toughness X/X, where X is your life total." - a layer 7b setting whose X is read
  now, whenever the creature's power is asked (so it follows the life total); modifications (counters, +N/+N) still add to it (613.4c).
* Dollmaker's Shop // Porcelain Gallery [2502] - "Creatures you control have base power and toughness each equal to the number of creatures you control." (the
  Gallery door's static, a Room's unlocked door: 709.5) - every creature you control, the count read now.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build, check, mana, pt, put, to_hand
from tests.wave45a_kit import FULL, cast, open_cards


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_aettir_and_priwen_sets_the_equipped_creature_to_the_life_total_and_follows_it(cards):
    s = build(cards, ["Aettir and Priwen", "Hill Giant"], [])
    aettir, giant = put(s, "Aettir and Priwen"), put(s, "Hill Giant")
    assert pt(s, "Hill Giant") == (3, 3)
    act(s, "p1", type="attach", card_ids=[aettir.id], to=giant.id)
    assert pt(s, "Hill Giant") == (40, 40)
    act(s, "p1", type="life", delta=-15)
    assert pt(s, "Hill Giant") == (25, 25)
    act(s, "p1", type="counter", card_ids=[giant.id], kind="+1/+1", delta=2)  # 613.4c: counters add to the base
    assert pt(s, "Hill Giant") == (27, 27)
    check(s)


def test_an_unequipped_creature_keeps_its_own_base(cards):
    s = build(cards, ["Aettir and Priwen", "Hill Giant", "Grizzly Bears"], [])
    aettir, giant = put(s, "Aettir and Priwen"), put(s, "Hill Giant")
    put(s, "Grizzly Bears")
    act(s, "p1", type="attach", card_ids=[aettir.id], to=giant.id)
    assert pt(s, "Grizzly Bears") == (2, 2)
    check(s)


def test_porcelain_gallery_sets_every_creature_you_control_to_the_number_of_creatures(cards):
    s = build(cards, ["Dollmaker's Shop // Porcelain Gallery", "Hill Giant", "Grizzly Bears", "Goblin Piker"], ["Shivan Dragon"])
    for name in ("Hill Giant", "Grizzly Bears", "Goblin Piker"):
        put(s, name)
    put(s, "Shivan Dragon", "p2")
    to_hand(s, "Dollmaker's Shop // Porcelain Gallery")
    mana(s, W=2, C=4)
    cast(s, "Dollmaker's Shop // Porcelain Gallery", face=1)
    assert [pt(s, n) for n in ("Hill Giant", "Grizzly Bears", "Goblin Piker")] == [(3, 3)] * 3  # three creatures: each 3/3 base
    assert pt(s, "Shivan Dragon", "p2") == (5, 5)  # (Bob's creature: not "you control")
    check(s)
