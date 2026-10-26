"""Wave 110N: Vodalian War Machine (602.2b the creatures tapped for its abilities are remembered for the turn, 603.10a its death trigger looks back)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

MACHINE, MERFOLK = "Vodalian War Machine", "Reef Merfolk"
EXTRA = [real(n, "{U}", 1, "Creature — Merfolk", "", ("1", "1"), "U") for n in (MERFOLK, "Merfolk Two", "Merfolk Three")]


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, EXTRA)


test_full = full_test([MACHINE])


def pump(s, machine, merfolk):
    act(s, "p1", type="activate_ability", card_id=machine.id, ability=2, cost_choices=[{"component": 0, "cards": [merfolk.id]}])
    answer(s)


def test_the_merfolk_tapped_this_turn_for_its_abilities_are_destroyed_when_it_dies(cards):
    s = build(cards, [MACHINE, "Murder", MERFOLK, "Merfolk Two", "Merfolk Three"])
    machine = put(s, MACHINE)
    a, b, c = (put(s, n) for n in (MERFOLK, "Merfolk Two", "Merfolk Three"))
    pump(s, machine, a)
    pump(s, machine, b)
    mana(s, "p1", B=3)
    cast(s, "Murder", [machine.id], pay=False)
    answer(s)
    assert zone_of(s, MACHINE) == "p1:graveyard"
    assert (zone_of(s, MERFOLK), zone_of(s, "Merfolk Two"), zone_of(s, "Merfolk Three")) == ("p1:graveyard", "p1:graveyard", "p1:battlefield")
    check(s)


def test_a_merfolk_tapped_on_an_earlier_turn_is_not_destroyed(cards):
    s = build(cards, [MACHINE, "Murder", MERFOLK])
    machine = put(s, MACHINE)
    a = put(s, MERFOLK)
    pump(s, machine, a)
    next_turn(s)
    mana(s, "p1", B=3)
    cast(s, "Murder", [machine.id], pay=False)
    answer(s)
    assert zone_of(s, MACHINE) == "p1:graveyard" and zone_of(s, MERFOLK) == "p1:battlefield"
    check(s)
