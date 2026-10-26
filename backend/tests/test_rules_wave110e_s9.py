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
DJINN = real("Djinn Illuminatus", "{3}{U/R}{U/R}", 5, "Creature — Djinn",
             "({U/R} can be paid with either {U} or {R}.)\nFlying\nEach instant and sorcery spell you cast has replicate. The replicate cost is equal to its mana cost. "
             "(When you cast it, copy it for each time you paid its replicate cost. You may choose new targets for the copies.)", ("3", "5"), "UR")
SIP = real("Test Sip", "{U}", 1, "Instant", "You gain 1 life.", None, "U")
BOLT = real("Test Tonic", "{1}{G}", 2, "Sorcery", "You gain 1 life.", None, "G")
base.EXTRA.extend([BATTLE, BEAR, DJINN, SIP, BOLT])


@pytest.mark.parametrize("name", [c["name"] for c in (BATTLE, DJINN)])
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


@pytest.mark.parametrize(("spell", "cost"), [("Test Sip", {"U": 3}), ("Test Tonic", {"G": 3, "C": 3})])
def test_djinn_illuminatus_gives_instants_and_sorceries_replicate(cards, spell, cost):
    """702.56a: the spell has replicate (cost = its mana cost); each time paid, one copy (two payments: 3 life in all)."""
    from tests.game_helpers import act
    from tests.wave9c_kit import life

    s = build(cards, ["Djinn Illuminatus", spell])
    put(s, "Djinn Illuminatus")
    mana(s, **cost)
    before = life(s, "p1")
    act(s, "p1", type="cast_spell", card_id=to_hand(s, spell).id, kicker=2)
    answer(s)
    assert life(s, "p1") == before + 3
    check(s)


def test_djinn_illuminatus_gives_no_replicate_to_creature_spells(cards):
    from app.game.errors import ActionError
    from tests.game_helpers import act

    s = build(cards, ["Djinn Illuminatus", "Test Bear"])
    put(s, "Djinn Illuminatus")
    mana(s, G=3, C=3)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Test Bear").id, kicker=1)
