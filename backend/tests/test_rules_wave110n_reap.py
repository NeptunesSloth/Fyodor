"""Wave 110N: Reap (601.2c the number of targets is X as the targets are chosen: the black permanents of the opponent chosen first)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

REAP = "Reap"
EXTRA = [real("Night Squire", "{1}{B}", 2, "Creature — Human", "", ("2", "2"), "B"), real("Dusk Squire", "{1}{B}", 2, "Creature — Human", "", ("2", "2"), "B"), real("Dawn Squire", "{1}{W}", 2, "Creature — Human", "", ("2", "2"), "W")]


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, EXTRA)


test_full = full_test([REAP])


def setup(cards, black):
    s = build(cards, [REAP, "Grizzly Bears", "Llanowar Elves", "Murder", "Lightning Bolt", "Night Squire"], ["Dusk Squire", "Dawn Squire", "Murder"])
    for n in ["Grizzly Bears", "Llanowar Elves", "Murder", "Lightning Bolt"]:
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"player": "p1", "zone": "graveyard"})
    if black >= 1:
        put(s, "Dusk Squire", "p2")
    put(s, "Dawn Squire", "p2")  # (white: not counted)
    put(s, "Night Squire")  # (black, but Alice's: Reap counts the target opponent's)
    return s


@pytest.mark.parametrize("black", [0, 1])
def test_up_to_as_many_cards_as_the_opponent_has_black_permanents(cards, black):
    s = setup(cards, black)
    gy = [card_named(s, n).id for n in ["Grizzly Bears", "Llanowar Elves"]]
    cast(s, REAP, ["p2", *gy[: black]], target_counts=[1, black])
    answer(s)
    assert sum(1 for c in gy if s.state.cards[c].zone == "p1:hand") == black
    check(s)


def test_more_cards_than_black_permanents_cannot_be_targeted(cards):
    s = setup(cards, 1)
    gy = [card_named(s, n).id for n in ["Grizzly Bears", "Llanowar Elves"]]
    with pytest.raises(ActionError):
        cast(s, REAP, ["p2", *gy], target_counts=[1, 2])
    check(s)


def test_zero_cards_is_allowed_and_the_x_is_the_opponents_not_yours(cards):
    s = setup(cards, 0)
    cast(s, REAP, ["p2"], target_counts=[1, 0])
    answer(s)
    assert zone_of(s, "Grizzly Bears") == "p1:graveyard"
    check(s)
