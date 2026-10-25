"""Wave 110F: promotions on real Oracle text. Every scenario checks the replay and a save and a load (tests/wave9c_kit.check).

* 601.2c, 205.3m, 701.14a: "Choose two target creatures that share no creature types. Those creatures fight each other." (Rivals' Duel).
* 608.2b, 105.2: "Destroy two target nonblack creatures unless either one is a color the other isn't. They can't be regenerated." (Dead Ringers).
* 603.10a, 509.1g: "When this creature dies during combat, it deals 6 damage to each creature it blocked this combat." (Cathedral Membrane).
* 611.2a, 508.1d: "During target player's next turn, creatures that player controls attack you if able." (Taunt).
* 601.3, 506.3, 122.1: "Cast this spell only after combat." + control change of a creature that attacked you + -1/-0 counter (Jabari's Influence).
* 602.5, 605.1a: "Creatures with flying can't attack or block, and their activated abilities with {T} in their costs can't be activated." (Katabatic Winds).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave34b_activated import attack
from tests.test_rules_wave100f_attached import to_phase
from tests.test_rules_wave100f_gear import block
from tests.test_rules_wave100n_multi import EXTRA as _BASE
from tests.test_rules_wave100n_multi import (
    answer,
    card_db,  # noqa: F401  (fixture DB with EXTRA)
    cast,
)
from tests.wave9c_kit import build, check, mana, put, to_hand, zone_of

EXTRA = [
    real('Katabatic Winds', '{2}{G}', 3, 'Enchantment',
         "Creatures with flying can't attack or block, and their activated abilities with {T} in their costs can't be activated.", None, 'G'),
    real("Rivals' Duel", '{3}{R}', 4, 'Sorcery',
         "Choose two target creatures that share no creature types. Those creatures fight each other.", None, 'R'),
    real('Test Giant 110F', '{3}{R}', 4, 'Creature — Giant', 'Vigilance', ('3', '3'), 'R'),
    real('Dead Ringers', '{3}{B}{B}', 5, 'Sorcery',
         "Destroy two target nonblack creatures unless either one is a color the other isn't. They can't be regenerated.", None, 'B'),
    real('Cathedral Membrane', '{1}{W/P}', 2, 'Artifact Creature — Phyrexian Wall',
         "({W/P} can be paid with either {W} or 2 life.)\nDefender\nWhen this creature dies during combat, it deals 6 damage to each creature it blocked this combat.", ('0', '3'), 'W'),
    real('Taunt', '{U}', 1, 'Instant',
         "During target player's next turn, creatures that player controls attack you if able.", None, 'U'),
    real("Jabari's Influence", '{3}{U}{U}', 5, 'Instant',
         "Cast this spell only after combat.\nGain control of target nonartifact, nonblack creature that attacked you this turn and put a -1/-0 counter on it.", None, 'U'),
    real('Test Flyer', '{2}{U}', 3, 'Creature — Bird', 'Flying\n{T}: Draw a card.', ('1', '1'), 'U'),
]
_BASE.extend(EXTRA)  # the shared fixture DB builder reads this list
NAMES = ["Katabatic Winds", "Rivals' Duel", "Dead Ringers", "Cathedral Membrane", "Taunt", "Jabari's Influence"]


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("creature,blocked", [("Test Flyer", True), ("Llanowar Elves", False)])
def test_katabatic_winds_stops_flyers_tap_abilities(cards, creature, blocked):
    s = build(cards, ["Katabatic Winds", creature])
    it = put(s, creature)
    c = to_hand(s, "Katabatic Winds")
    mana(s, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[])
    act(s, "p1", type="pass_priority")
    from tests.test_rules_wave100f_control import ch
    ab = next(x for x in ch(s, it).abilities if x.text.startswith("{T}"))
    if blocked:
        with pytest.raises(ActionError, match="can't be activated"):
            act(s, "p1", type="activate_ability", card_id=it.id, ability=ab.index)
    else:  # (Llanowar Elves is only summoning sick: the Winds don't touch it)
        with pytest.raises(ActionError, match="summoning sickness"):
            act(s, "p1", type="activate_ability", card_id=it.id, ability=ab.index)
    check(s)


def duel(cards, mine, theirs):
    s = build(cards, ["Rivals' Duel", mine], [theirs])
    a, b = put(s, mine), put(s, theirs, "p2")
    mana(s, R=1, C=3)
    return s, a, b


def test_rivals_duel_fights_unrelated_creatures(cards):
    s, bear, giant = duel(cards, "Grizzly Bears", "Test Giant 110F")
    cast(s, "Rivals' Duel", [bear.id, giant.id], target_counts=[2])
    answer(s)
    assert zone_of(s, "Grizzly Bears") == "p1:graveyard" and zone_of(s, "Test Giant 110F", "p2") == "p2:battlefield"
    check(s)


def test_rivals_duel_refuses_creatures_sharing_a_type(cards):
    s, bear, bear2 = duel(cards, "Grizzly Bears", "Grizzly Bears")
    with pytest.raises(ActionError, match="share no creature type"):
        cast(s, "Rivals' Duel", [bear.id, bear2.id], target_counts=[2])


@pytest.mark.parametrize("second,dies", [("Test Giant 110F", False), ("Grizzly Bears", True)])
def test_dead_ringers_needs_the_same_colors(cards, second, dies):
    s = build(cards, ["Dead Ringers", "Grizzly Bears"], [second])
    a, b = put(s, "Grizzly Bears"), put(s, second, "p2")
    mana(s, B=2, C=3)
    cast(s, "Dead Ringers", [a.id, b.id], target_counts=[2])
    answer(s)
    assert (zone_of(s, "Grizzly Bears") == "p1:graveyard") is dies
    check(s)


def test_cathedral_membrane_hits_what_it_blocked_when_it_dies(cards):
    s = build(cards, ["Test Giant 110F"], ["Cathedral Membrane", "Taunt"])
    giant, wall = put(s, "Test Giant 110F"), put(s, "Cathedral Membrane", "p2")
    attack(s, giant)
    block(s, (wall, giant))
    answer(s)
    assert zone_of(s, "Cathedral Membrane", "p2") == "p2:graveyard" and zone_of(s, "Test Giant 110F") == "p1:graveyard"
    check(s)


@pytest.mark.parametrize("taunted", [True, False])
def test_taunt_forces_the_target_players_creatures_to_attack_next_turn(cards, taunted):
    s = build(cards, ["Taunt"], ["Grizzly Bears"])
    bear = put(s, "Grizzly Bears", "p2")
    if taunted:
        mana(s, U=1)
        cast(s, "Taunt", ["p2"])
        answer(s)
    to_phase(s, "declare_attackers", turn=2)
    if taunted:
        with pytest.raises(ActionError):
            act(s, "p2", type="declare_attackers", attackers=[])
        act(s, "p2", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p1"}])
    else:
        act(s, "p2", type="declare_attackers", attackers=[])
    check(s)


@pytest.mark.parametrize("phase,ok", [("declare_attackers", False), ("main2", True)])
def test_jabaris_influence_after_combat_steals_the_attacker(cards, phase, ok):
    s = build(cards, ["Grizzly Bears"], ["Jabari's Influence"])
    bear = put(s, "Grizzly Bears")
    attack(s, bear)
    if ok:
        for pid in ("p1", "p2"):
            act(s, pid, type="set_prefs", response="on")  # (p2 must get priority in the second main phase)
        to_phase(s, phase)
        act(s, "p1", type="pass_priority")
    mana(s, "p2", U=2, C=3)
    if ok:
        cast(s, "Jabari's Influence", [bear.id], pid="p2")
        answer(s)
        assert zone_of(s, "Grizzly Bears") == "p2:battlefield"
        assert s.state.cards[bear.id].counters.get("-1/-0") == 1
        check(s)
    else:
        with pytest.raises(ActionError):
            cast(s, "Jabari's Influence", [bear.id], pid="p2")
