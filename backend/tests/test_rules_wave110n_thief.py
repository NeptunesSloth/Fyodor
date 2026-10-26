"""Wave 110N: Thief of Existence (601.2i cast trigger, 400.7a: the ability the spell gains is kept by the permanent it becomes)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

THIEF, SMALL, BIG = "Thief of Existence", "Cheap Relic", "Costly Relic"
EXTRA = [
    real(THIEF, "{4}{B}", 5, "Creature — Eldrazi Rogue",
         "Devoid (This card has no color.)\nWhen you cast this spell, exile up to one target noncreature, nonland permanent an opponent controls with mana value 4 or less. "
         "If you do, Thief of Existence gains \"When this creature leaves the battlefield, target opponent draws a card.\"", ("4", "4"), ""),
    real(SMALL, "{4}", 4, "Artifact", "", None),
    real(BIG, "{5}", 5, "Artifact", "", None),
]


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, EXTRA)


test_full = full_test([THIEF])


def leave(s, c):
    """Alice's own Murder on it (a leaves-the-battlefield trigger needs a real destruction, not a table move)."""
    mana(s, "p1", B=3)
    cast(s, "Murder", [c.id], pay=False)
    answer(s)


@pytest.mark.parametrize("exile", [True, False])
def test_thief_draws_for_the_opponent_when_it_leaves_only_if_it_exiled(cards, exile):
    s = build(cards, [THIEF, "Murder"], [SMALL])
    relic = put(s, SMALL, "p2")
    hand = len(s.state.zones["p2:hand"])
    thief = cast(s, THIEF)
    answer(s, [relic.id] if exile else [])  # the cast trigger's "up to one target"
    assert zone_of(s, SMALL, "p2") == ("p2:exile" if exile else "p2:battlefield")
    assert zone_of(s, THIEF) == "p1:battlefield"
    pass
    leave(s, thief)
    assert len(s.state.zones["p2:hand"]) == hand + (1 if exile else 0)
    check(s)


def test_the_exiled_permanent_must_have_mana_value_4_or_less(cards):
    s = build(cards, [THIEF], [BIG])
    put(s, BIG, "p2")
    cast(s, THIEF)
    assert s.state.rules.decision is None  # no legal target: the trigger is removed from the stack (603.3d)
    answer(s)
    assert zone_of(s, BIG, "p2") == "p2:battlefield" and zone_of(s, THIEF) == "p1:battlefield"
    check(s)
