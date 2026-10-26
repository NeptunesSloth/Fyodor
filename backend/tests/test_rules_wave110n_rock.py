"""Wave 110N: Rock Jockey (601.3, 305.1: no cast after a land play, no land play after it was cast)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

ROCK = "Rock Jockey"
EXTRA = [real(ROCK, "{2}{R}", 3, "Creature — Goblin Rogue",
              "You can't cast Rock Jockey if you've played a land this turn.\nYou can't play lands if this creature was cast this turn.", ("3", "3"), "R")]


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, EXTRA)


test_full = full_test([ROCK])


def land(s, name="Mountain"):
    c = to_hand(s, name)
    act(s, "p1", type="play_land", card_id=c.id)


def test_cant_be_cast_after_a_land_play(cards):
    s = build(cards, [ROCK, "Mountain"])
    land(s)
    with pytest.raises(ActionError, match="played a land"):
        cast(s, ROCK)
    check(s)


def test_can_be_cast_before_a_land_play_but_then_no_land_this_turn(cards):
    s = build(cards, [ROCK, "Mountain"])
    cast(s, ROCK)
    answer(s)
    assert zone_of(s, ROCK) == "p1:battlefield"
    with pytest.raises(ActionError, match="cast this turn"):
        land(s)
    check(s)


def test_lands_can_be_played_in_a_later_turn(cards):
    s = build(cards, [ROCK, "Mountain"])
    cast(s, ROCK)
    answer(s)
    next_turn(s)
    land(s)
    assert zone_of(s, "Mountain") == "p1:battlefield"
    check(s)


def test_a_rock_jockey_put_onto_the_battlefield_was_not_cast(cards):
    s = build(cards, [ROCK, "Mountain"])
    put(s, ROCK)
    land(s)
    assert zone_of(s, "Mountain") == "p1:battlefield"
    check(s)
