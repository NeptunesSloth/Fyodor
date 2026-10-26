"""Wave 110N: Eriette, the Beguiler (611.2b control lasts only while that Aura is attached to it; the mana value limit is part of the event, 603.2)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

ERIETTE, AURA, EQUAL, BIGGER = "Eriette, the Beguiler", "Binding Veil", "Three Squire", "Four Squire"
EXTRA = [
    real(ERIETTE, "{1}{W}{U}{B}", 4, "Legendary Creature — Human Warlock",
         "Lifelink\nWhenever an Aura you control becomes attached to a nonland permanent an opponent controls with mana value less than or equal to that Aura's mana value, "
         "gain control of that permanent for as long as that Aura is attached to it.", ("3", "3"), "WUB"),
    real(AURA, "{2}{W}", 3, "Enchantment — Aura", "Enchant creature", None, "W"),
    real("Dispel Aura", "{W}", 1, "Instant", "Destroy target Aura.", None, "W"),
    real(EQUAL, "{2}{G}", 3, "Creature — Human", "", ("3", "3"), "G"),
    real(BIGGER, "{3}{G}", 4, "Creature — Human", "", ("4", "4"), "G"),
]


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, EXTRA)


test_full = full_test([ERIETTE])


def controller(s, c):
    return s.state.cards[c.id].controller


@pytest.mark.parametrize(("victim", "taken"), [("Grizzly Bears", True), (EQUAL, True), (BIGGER, False)])
def test_gains_control_only_of_permanents_with_mana_value_up_to_the_auras(cards, victim, taken):
    s = build(cards, [ERIETTE, AURA], [victim])
    put(s, ERIETTE)
    target = put(s, victim, "p2")
    cast(s, AURA, [target.id])
    answer(s)
    assert controller(s, target) == ("p1" if taken else "p2")
    check(s)


def test_control_ends_when_the_aura_leaves(cards):
    s = build(cards, [ERIETTE, AURA, "Dispel Aura"], ["Grizzly Bears"])
    put(s, ERIETTE)
    target = put(s, "Grizzly Bears", "p2")
    aura = cast(s, AURA, [target.id])
    answer(s)
    assert controller(s, target) == "p1"
    cast(s, "Dispel Aura", [aura.id])
    answer(s)
    assert zone_of(s, AURA) == "p1:graveyard" and controller(s, target) == "p2"
    check(s)


def test_an_aura_on_your_own_creature_does_nothing(cards):
    s = build(cards, [ERIETTE, AURA, "Grizzly Bears"])
    put(s, ERIETTE)
    mine = put(s, "Grizzly Bears")
    cast(s, AURA, [mine.id])
    answer(s)
    assert controller(s, mine) == "p1" and not s.state.zones.get("stack")
    check(s)
