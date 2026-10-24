"""Wave 100E: X damage divided as you choose (app/rules/xdamage100e.py; CR 2026-09-25). Real Oracle text
(tests/fixtures/wave100e_xdamage_cards.json); every scenario checks the replay and a save and a load.

* 601.2d: the division is announced as the spell is cast or the ability activated; an X the text defines is fixed then (Impact Resonance).
* "dealt damage this way": what was actually dealt (after prevention): tapped / can't block / can't cast noncreature spells this turn.
"""

from __future__ import annotations

import pytest

from tests import wave100e_kit as kit
from tests.game_helpers import act
from tests.test_rules_wave7b_activation import ability_index
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand
from tests.wave100e_kit import answer, can_cast, chars, full_control, loyal, zone_of


@pytest.fixture()
def cards(settings):
    yield from kit.repo(settings)


def test_aurelias_fury_taps_the_creatures_and_silences_the_players_dealt_damage(cards):
    """X 4 divided: 2 to a 0/6 wall (tapped), 2 to Bob (no noncreature spells this turn; creature spells still), nothing to Alice's untouched
    Bears (not dealt damage: untapped)."""
    s = build(cards, ["Aurelia's Fury", "Grizzly Bears"], ["Probe Wall", "Lightning Bolt", "Ambush Viper"])
    bears = put(s, "Grizzly Bears")
    wall = put(s, "Probe Wall", "p2")
    bolt, viper = to_hand(s, "Lightning Bolt", "p2"), to_hand(s, "Ambush Viper", "p2")
    spell = to_hand(s, "Aurelia's Fury")
    mana(s, R=1, W=1, C=4)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[wall.id, "p2"], target_counts=[2], division=[2, 2], x_value=4)
    answer(s)
    assert s.state.cards[wall.id].tapped and s.state.cards[wall.id].damage == 2 and life(s, "p2") == 38
    assert not s.state.cards[bears.id].tapped
    mana(s, "p2", R=1, G=2)
    assert not can_cast(s, "p2", bolt) and can_cast(s, "p2", viper)  # (a creature spell with flash still can)
    check(s)


def test_aurelias_fury_an_illegal_target_keeps_its_share_and_isnt_tapped(cards):
    """The 2013-01-24 rulings: a target that left is dealt nothing and the others keep their announced shares."""
    s = build(cards, ["Aurelia's Fury"], ["Probe Wall", "Grizzly Bears"])
    wall, bears = put(s, "Probe Wall", "p2"), put(s, "Grizzly Bears", "p2")
    spell = to_hand(s, "Aurelia's Fury")
    mana(s, R=1, W=1, C=3)
    full_control(s)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[wall.id, bears.id], target_counts=[2], division=[1, 2], x_value=3)
    act(s, "p2", type="move", card_ids=[bears.id], to={"player": "p2", "zone": "hand"})
    answer(s)
    assert s.state.cards[wall.id].damage == 1 and s.state.cards[wall.id].tapped and zone_of(s, bears) == "p2:hand"
    check(s)


def test_huatli_divides_x_and_the_creatures_dealt_damage_cant_block(cards):
    s = build(cards, ["Huatli, Warrior Poet"], ["Probe Wall", "Twisted Abomination"])
    huatli = loyal(s, "Huatli, Warrior Poet")
    wall, big = put(s, "Probe Wall", "p2"), put(s, "Twisted Abomination", "p2")
    act(s, "p1", type="activate_ability", card_id=huatli.id, ability=ability_index(s, huatli, "divided as you choose"), x_value=3,
        targets=[wall.id, big.id], target_counts=[2], division=[1, 2])
    answer(s)
    assert s.state.cards[wall.id].damage == 1 and s.state.cards[big.id].damage == 2
    assert "cant_block" in chars(s, wall).imposed and "cant_block" in chars(s, big).imposed
    check(s)


def test_huatli_a_creature_with_its_damage_prevented_can_still_block(cards):
    """"dealt damage this way": only creatures actually dealt damage (615) — the Bears' share removed from the battlefield isn't dealt."""
    s = build(cards, ["Huatli, Warrior Poet"], ["Probe Wall", "Grizzly Bears"])
    huatli = loyal(s, "Huatli, Warrior Poet")
    wall, bears = put(s, "Probe Wall", "p2"), put(s, "Grizzly Bears", "p2")
    full_control(s)
    act(s, "p1", type="activate_ability", card_id=huatli.id, ability=ability_index(s, huatli, "divided as you choose"), x_value=2,
        targets=[wall.id, bears.id], target_counts=[2], division=[1, 1])
    act(s, "p2", type="move", card_ids=[bears.id], to={"player": "p2", "zone": "hand"})
    answer(s)
    assert "cant_block" in chars(s, wall).imposed and zone_of(s, bears) == "p2:hand"
    check(s)


def test_impact_resonance_x_is_the_most_one_source_dealt_one_thing_this_turn(cards):
    """Two Lightning Bolts to Bob from two sources (3 each), then a Wall dealt 3 by one: X is 3 (each source and recipient on its own), divided 1 + 2."""
    s = build(cards, ["Impact Resonance", "Lightning Bolt"], ["Probe Wall", "Grizzly Bears"])
    wall, bears = put(s, "Probe Wall", "p2"), put(s, "Grizzly Bears", "p2")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=["p2"])
    answer(s)
    spell = to_hand(s, "Impact Resonance")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[wall.id, bears.id], target_counts=[2], division=[1, 2])
    answer(s)
    assert s.state.cards[wall.id].damage == 1 and zone_of(s, bears) == "p2:graveyard"
    check(s)


def test_impact_resonance_with_no_damage_this_turn_has_nothing_to_divide(cards):
    s = build(cards, ["Impact Resonance"], ["Probe Wall"])
    wall = put(s, "Probe Wall", "p2")
    spell = to_hand(s, "Impact Resonance")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[], target_counts=[0], division=[])
    answer(s)
    assert s.state.cards[wall.id].damage == 0 and card_named(s, "Impact Resonance").zone == "p1:graveyard"
    check(s)
