"""Wave 110E session 9: Oracle-text scenarios for cards promoted this session (each docstring names the rule)."""
from __future__ import annotations

import pytest

import tests.test_rules_wave110e_cards as base
from app.rules import coverage
from tests.test_rules_wave110e_cards import answer, card_db  # noqa: F401  (the fixture)
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

BATTLE = real("Uphill Battle", "{3}{R}", 4, "Enchantment", "Creatures played by your opponents enter tapped.", None, "R")
BEAR = real("Test Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G")
base.EXTRA.extend([BATTLE, BEAR])


@pytest.mark.parametrize("name", [c["name"] for c in (BATTLE,)])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _cast_bear(cards, battle_owner):
    s = build(cards, ["Test Bear", *(["Uphill Battle"] if battle_owner == "p1" else [])], ["Uphill Battle"] if battle_owner == "p2" else [])
    from tests.game_helpers import act

    put(s, "Uphill Battle", battle_owner)
    mana(s, G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Test Bear").id)
    answer(s)
    return s, card_named(s, "Test Bear")


def test_uphill_battle_opponents_cast_creature_enters_tapped(cards):
    """614.1d, 305.1: a creature an opponent of the controller casts enters tapped."""
    s, bear = _cast_bear(cards, "p2")
    assert s.state.cards[bear.id].zone == "p1:battlefield" and s.state.cards[bear.id].tapped
    check(s)


def test_uphill_battle_own_cast_and_non_cast_entries_untapped(cards):
    """Its controller's creatures are not "played by your opponents"; a creature put onto the battlefield (not cast) enters untapped."""
    s, bear = _cast_bear(cards, "p1")
    assert s.state.cards[bear.id].zone == "p1:battlefield" and not s.state.cards[bear.id].tapped
    s = build(cards, ["Test Bear"], ["Uphill Battle"])
    put(s, "Uphill Battle", "p2")
    bear = put(s, "Test Bear")
    assert not s.state.cards[bear.id].tapped
    check(s)
