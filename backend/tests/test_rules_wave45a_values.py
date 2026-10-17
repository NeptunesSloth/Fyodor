"""Wave 45A: "the difference between that creature's power and its toughness" (CR 2026-09-25), real Oracle text (tests/fixtures/wave45a_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 608.2h: "Whenever a creature you control enters, target opponent loses life equal to the difference between that creature's power and its toughness." (Jaws of Defeat
  [4226]) - the creature as it entered; how far apart the two are (never negative); nothing when they are equal.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.test_rules_wave34b_activated import settle
from tests.wave9c_kit import build, check, mana, put, to_hand
from tests.wave45a_kit import FULL, cast, life, open_cards


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


@pytest.mark.parametrize("creature, cost, lost", [("Wall of Omens", {"W": 1, "C": 1}, 4), ("Goblin Piker", {"R": 1, "C": 1}, 1), ("Hill Giant", {"R": 1, "C": 3}, 0)])
def test_jaws_of_defeat_costs_the_opponent_the_gap_between_power_and_toughness(cards, creature, cost, lost):
    s = build(cards, ["Jaws of Defeat", creature], [])
    put(s, "Jaws of Defeat")
    to_hand(s, creature)
    mana(s, **cost)
    cast(s, creature)  # (the one opponent is the trigger's target)
    settle(s)
    assert life(s, "p2") == 40 - lost
    check(s)
