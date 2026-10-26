"""Wave 110M: a target restriction on the kind of spell or ability. Wall of Shadows: "This creature can't be the target of spells that can target only Walls or of abilities
that can target only Walls." A spell or ability whose target (115.1) can only be a Wall can't pick it (115.2); anything that can also target other things still can.
Every scenario checks the replay and a save and a load.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.wave110m_kit import *

SHADOWS = "Wall of Shadows"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([SHADOWS])


def table(cards):
    s = build(cards, [SHADOWS, "Test Wall", "Test Wall Pump", "Lightning Bolt", "Giant Growth"], ["Elite Vanguard"], forests=20)
    return s, put(s, SHADOWS), put(s, "Test Wall")


def test_a_spell_that_can_only_target_walls_cannot_target_wall_of_shadows(cards):
    s, shadows, wall = table(cards)
    with pytest.raises(ActionError):
        cast(s, "Test Wall Pump", [shadows.id])
    cast(s, "Test Wall Pump", [wall.id])  # (any other Wall is fine)
    answer(s)
    assert ch(s, wall).pt == (2, 6)
    check(s)


def test_a_spell_that_can_target_more_than_walls_can_target_it(cards):
    s, shadows, wall = table(cards)
    cast(s, "Giant Growth", [shadows.id])
    answer(s)
    assert ch(s, shadows).pt == (3, 4)
    cast(s, "Lightning Bolt", [shadows.id])
    answer(s)
    assert s.state.cards[shadows.id].damage == 3  # (a 3/4 now: the Bolt can target it too)
    check(s)
