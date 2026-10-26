"""Wave 110M: a target restriction on the kind of spell or ability. Wall of Shadows: "This creature can't be the target of spells that can target only Walls or of abilities
that can target only Walls." A spell or ability whose target (115.1) can only be a Wall can't pick it (115.2); anything that can also target other things still can.
Every scenario checks the replay and a save and a load.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.wave36a_kit import ready
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


# -- Grip of Chaos -----------------------------------------------------------------------------------------------------------------------------
GRIP = "Grip of Chaos"
test_grip_full = full_test([GRIP])


def aim(monkeypatch, target):
    """The table's random pick: always ``target`` (when it is among the legal ones)."""
    from app.rules import wave110m_cards

    seen = []

    def pick(options):
        seen.append(sorted(options))
        return target if target in options else sorted(options)[0]

    monkeypatch.setattr(wave110m_cards, "pick_random", pick)
    return seen


def grip_table(cards, mine=("Lightning Bolt",)):
    s = build(cards, [GRIP, *mine], ["Elite Vanguard"], forests=20)
    put(s, GRIP)
    return s, put(s, "Elite Vanguard", "p2")


def test_grip_reselects_a_spells_single_target_from_all_the_legal_ones(cards, monkeypatch):
    s, vanguard = grip_table(cards)
    seen = aim(monkeypatch, vanguard.id)
    cast(s, "Lightning Bolt", ["p2"])
    answer(s)
    assert zone_of(s, "Elite Vanguard", "p2") == "p2:graveyard" and life(s, "p2") == 40  # (the Bolt was aimed at Bob and landed on the Vanguard)
    assert sorted(["p1", "p2", vanguard.id]) == seen[0]  # (every legal target: both players and the creature, the original one too)
    check(s)


def test_grip_may_pick_the_target_it_already_has(cards, monkeypatch):
    s, vanguard = grip_table(cards)
    aim(monkeypatch, "p2")
    cast(s, "Lightning Bolt", ["p2"])
    answer(s)
    assert life(s, "p2") == 37 and zone_of(s, "Elite Vanguard", "p2") == "p2:battlefield"
    check(s)


def test_grip_leaves_a_spell_with_two_targets_alone(cards, monkeypatch):
    s, vanguard = grip_table(cards, ["Test Fight", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    seen = aim(monkeypatch, "p2")
    cast(s, "Test Fight", [bears.id, vanguard.id], target_counts=[1, 1])
    answer(s)
    assert zone_of(s, "Elite Vanguard", "p2") == "p2:graveyard" and not seen
    check(s)


def test_grip_reselects_the_single_target_of_an_activated_ability(cards, monkeypatch):
    s, vanguard = grip_table(cards, ["Millstone"])
    stone = put(s, "Millstone")
    ready(s, "Millstone")
    aim(monkeypatch, "p1")
    before = len(s.state.zones["p1:library"])
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=stone.id, ability=0, targets=["p2"])
    answer(s)
    assert len(s.state.zones["p1:library"]) == before - 2 and len(s.state.zones["p2:library"]) == len(s.state.zones["p2:library"])
    check(s)


def test_grip_reselects_a_triggered_abilitys_target(cards, monkeypatch):
    s, vanguard = grip_table(cards, ["Test Pinger"])
    aim(monkeypatch, vanguard.id)
    cast(s, "Test Pinger")
    answer(s, "p2")
    assert zone_of(s, "Elite Vanguard", "p2") == "p2:graveyard" and life(s, "p2") == 40  # (chosen as Bob, the ping landed on the 2/1)
    check(s)
