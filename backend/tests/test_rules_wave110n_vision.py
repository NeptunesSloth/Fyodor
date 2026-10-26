"""Wave 110N: Vision Charm (305.7 setting a land's type, 611.2c the lands are those of the first type as it resolves)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

CHARM = "Vision Charm"
EXTRA = [real(CHARM, "{U}", 1, "Instant",
              "Choose one —\n• Target player mills four cards.\n• Choose a land type and a basic land type. Each land of the first chosen type becomes the second chosen type until end of turn.\n"
              "• Target artifact phases out. (While it's phased out, it's treated as though it doesn't exist. It phases in before its controller untaps during their next untap step.)", None, "U"),
         real("Cheap Relic", "{2}", 2, "Artifact", "", None)]


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, EXTRA)


test_full = full_test([CHARM])


def subtypes(s, c):
    return ch(s, c).subtypes & {"Forest", "Island", "Mountain", "Plains", "Swamp"}


def pick(s, *ids):
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(ids))


def to_decision(s):
    """Pass priority until a decision opens (or the stack is empty)."""
    for _ in range(20):
        if s.state.rules.decision is not None or not s.state.zones.get("stack"):
            return s.state.rules.decision
        act(s, s.state.rules.priority, type="pass_priority")


def test_every_land_of_the_first_type_becomes_the_second_for_the_turn(cards):
    s = build(cards, [CHARM], forests=3, islands=3)
    put(s, "Forest")
    theirs = put(s, "Island", "p2")
    forests = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Forest"]
    cast(s, CHARM, modes=[1])
    to_decision(s)
    pick(s, "Forest")
    pick(s, "Island")
    answer(s)
    assert forests and all(subtypes(s, c) == {"Island"} for c in forests)
    assert subtypes(s, theirs) == {"Island"}
    check(s)


def test_lands_of_another_type_are_left_alone_and_it_ends_with_the_turn(cards):
    s = build(cards, [CHARM], forests=3, islands=3)
    forest = put(s, "Forest")
    isle = put(s, "Island", "p2")
    cast(s, CHARM, modes=[1])
    to_decision(s)
    pick(s, "Island")
    pick(s, "Mountain")
    answer(s)
    assert subtypes(s, isle) == {"Mountain"} and subtypes(s, forest) == {"Forest"}
    next_turn(s)
    assert subtypes(s, isle) == {"Island"}
    check(s)


def test_a_land_type_nothing_has_changes_nothing(cards):
    s = build(cards, [CHARM], forests=3, islands=3)
    forest = put(s, "Forest")
    cast(s, CHARM, modes=[1])
    to_decision(s)
    pick(s, "Desert")
    pick(s, "Swamp")
    answer(s)
    assert subtypes(s, forest) == {"Forest"}
    check(s)


def test_mill_four(cards):
    s = build(cards, [CHARM], forests=9, islands=9)
    before = len(s.state.zones["p2:library"])
    cast(s, CHARM, ["p2"], modes=[0])
    answer(s)
    assert len(s.state.zones["p2:library"]) == before - 4
    check(s)


def test_phase_out_an_artifact(cards):
    s = build(cards, [CHARM], ["Cheap Relic"])
    relic = put(s, "Cheap Relic", "p2")
    cast(s, CHARM, [relic.id], modes=[2])
    answer(s)
    assert s.state.cards[relic.id].zone.endswith(":phased")
    check(s)
