"""Wave 110F: promotions on real Oracle text. Every scenario checks the replay and a save and a load (tests/wave9c_kit.check).

* 601.2c, 205.3m, 701.14a: "Choose two target creatures that share no creature types. Those creatures fight each other." (Rivals' Duel).
* 608.2b, 105.2: "Destroy two target nonblack creatures unless either one is a color the other isn't. They can't be regenerated." (Dead Ringers).
* 603.10a, 509.1g: "When this creature dies during combat, it deals 6 damage to each creature it blocked this combat." (Cathedral Membrane).
* 611.2a, 508.1d: "During target player's next turn, creatures that player controls attack you if able." (Taunt).
* 601.3, 506.3, 122.1: "Cast this spell only after combat." + control change of a creature that attacked you + -1/-0 counter (Jabari's Influence).
* 400.7, 603.1: "At the beginning of your end step, exile up to one target artifact ... and up to one target creature ... Then return them ..." (Don & Leo).
* 702.23a, 613.1f, 702.7b: "Target creature gains first strike ... If it doesn't have rampage, that creature gains rampage 2 until end of turn." (Rapid Fire).
* 601.2h, 107.3: "create a number of ... tokens ... equal to the amount of mana spent to cast it" (Abby, Merciless Soldier).
* 702.26a-d: "Simultaneously, all phased-out creatures phase in and all creatures with phasing phase out." (Time and Tide).
* 118.1, 404.2, 701.19a: "Exile the top creature card of your graveyard: Regenerate this creature." (Zombie Scavengers).
* 603.2c, 607.2a: "Whenever you discard one or more cards, exile them from your graveyard." + "put the cards exiled with it into their owner's hand" (Toluz).
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
    real('Don & Leo, Problem Solvers', '{3}{W/U}{W/U}', 5, 'Legendary Creature — Mutant Ninja Turtle',
         "Vigilance\nAt the beginning of your end step, exile up to one target artifact you control and up to one target creature you control. Then return them to the battlefield under their owners' control.", ('4', '6'), 'WU'),
    real('Rapid Fire', '{3}{W}', 4, 'Instant',
         "Cast this spell only before blockers are declared.\nTarget creature gains first strike until end of turn. If it doesn't have rampage, that creature gains rampage 2 until end of turn. (Whenever the creature becomes blocked, it gets +2/+2 until end of turn for each creature blocking it beyond the first.)", None, 'W'),
    real('Time and Tide', '{U}{U}', 2, 'Instant',
         "Simultaneously, all phased-out creatures phase in and all creatures with phasing phase out.", None, 'U'),
    real('Test Fade 110F', '{U}', 1, 'Instant', "Target creature phases out.", None, 'U'),
    real('Test Phaser 110F', '{1}{U}', 2, 'Creature — Spirit', 'Phasing', ('2', '2'), 'U'),
    real('Abby, Merciless Soldier', '{1}{R}{G}', 3, 'Legendary Creature — Human Survivor',
         "When you cast this spell, create a number of 1/1 black Fungus Zombie creature tokens named Cordyceps Infected equal to the amount of mana spent to cast it.\nAbby enters under the control of an opponent of your choice.\nPartner\u2014Survivors (You can have two commanders if both have this ability.)", ('4', '4'), 'RG'),
    real('Zombie Scavengers', '{3}{B}', 4, 'Creature — Zombie',
         "Exile the top creature card of your graveyard: Regenerate this creature.", ('3', '3'), 'B'),
    real('Toluz, Clever Conductor', '{W/U}{U}{U/B}', 3, 'Legendary Creature — Human Rogue',
         "When Toluz enters, it connives. (Draw a card, then discard a card. If you discarded a nonland card, put a +1/+1 counter on this creature.)\nWhenever you discard one or more cards, exile them from your graveyard.\nWhen Toluz dies, put the cards exiled with it into their owner's hand.", ('3', '1'), 'WUB'),
    real('Test Flyer', '{2}{U}', 3, 'Creature — Bird', 'Flying\n{T}: Draw a card.', ('1', '1'), 'U'),
]
_BASE.extend(EXTRA)  # the shared fixture DB builder reads this list
NAMES = ["Katabatic Winds", "Rivals' Duel", "Dead Ringers", "Cathedral Membrane", "Taunt", "Jabari's Influence", "Don & Leo, Problem Solvers", "Rapid Fire", "Time and Tide", "Abby, Merciless Soldier", "Zombie Scavengers", "Toluz, Clever Conductor"]


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


def test_don_and_leo_blinks_the_chosen_artifact_and_creature_at_end_step(cards):
    s = build(cards, ["Don & Leo, Problem Solvers", "Grizzly Bears", "Sol Ring"])
    put(s, "Don & Leo, Problem Solvers")
    bear, ring = put(s, "Grizzly Bears"), put(s, "Sol Ring")
    before = [s.state.rules.object_id(c.id) for c in (bear, ring)]
    to_phase(s, "end")
    answer(s, ring.id, bear.id)  # (the artifact, then the creature: Don & Leo itself is also a legal creature)
    assert [zone_of(s, n) for n in ("Grizzly Bears", "Sol Ring")] == ["p1:battlefield"] * 2
    assert all(s.state.rules.object_id(c.id) != b for c, b in zip((bear, ring), before, strict=True))  # 400.7: new objects
    check(s)


def test_rapid_fire_grants_rampage_and_first_strike(cards):
    s = build(cards, ["Rapid Fire", "Grizzly Bears"], ["Llanowar Elves", "Test Giant 110F"])
    bear = put(s, "Grizzly Bears")
    elf, giant = put(s, "Llanowar Elves", "p2"), put(s, "Test Giant 110F", "p2")
    to_phase(s, "main1", turn=3)  # (the Bears are summoning sick before)
    mana(s, W=1, C=3)
    cast(s, "Rapid Fire", [bear.id])
    answer(s)
    attack(s, bear)
    block(s, (elf, bear), (giant, bear))
    while s.state.zones.get("stack"):  # (resolve the rampage trigger; stop before the damage division)
        act(s, s.state.rules.priority, type="pass_priority")
    from tests.test_rules_wave100f_control import ch
    assert "first strike" in ch(s, bear).keywords
    assert ch(s, bear).pt == (4, 4)  # 2/2 + 2/2 for the second blocker (702.23a)
    check(s)


def test_rapid_fire_twice_grants_rampage_once(cards):
    """702.23c: a second Rapid Fire sees the granted rampage, so only one rampage 2 trigger happens."""
    s = build(cards, ["Rapid Fire", "Rapid Fire", "Grizzly Bears"], ["Llanowar Elves", "Test Giant 110F"])
    bear = put(s, "Grizzly Bears")
    elf, giant = put(s, "Llanowar Elves", "p2"), put(s, "Test Giant 110F", "p2")
    to_phase(s, "main1", turn=3)
    mana(s, W=2, C=6)
    for _ in range(2):
        cast(s, "Rapid Fire", [bear.id])
        answer(s)
    attack(s, bear)
    block(s, (elf, bear), (giant, bear))
    while s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    from tests.test_rules_wave100f_control import ch
    assert ch(s, bear).pt == (4, 4)  # one rampage 2, not two
    check(s)


def test_time_and_tide_swaps_phased_out_and_phasing_creatures(cards):
    s = build(cards, ["Time and Tide", "Test Fade 110F", "Test Phaser 110F", "Grizzly Bears"])
    put(s, "Test Phaser 110F")
    bear = put(s, "Grizzly Bears")
    mana(s, U=3)
    cast(s, "Test Fade 110F", [bear.id])
    answer(s)
    assert zone_of(s, "Grizzly Bears") == "p1:phased"
    cast(s, "Time and Tide")
    answer(s)
    assert zone_of(s, "Grizzly Bears") == "p1:battlefield" and zone_of(s, "Test Phaser 110F") == "p1:phased"
    check(s)


def test_abby_makes_a_token_per_mana_spent_and_enters_under_an_opponent(cards):
    s = build(cards, ["Abby, Merciless Soldier"])
    mana(s, R=1, G=1, C=1)
    cast(s, "Abby, Merciless Soldier")
    answer(s)
    tokens = [c for c in s.state.cards.values() if c.name == "Cordyceps Infected" and c.zone == "p1:battlefield"]
    assert len(tokens) == 3
    assert zone_of(s, "Abby, Merciless Soldier") == "p2:battlefield"
    check(s)


def test_zombie_scavengers_exiles_only_the_top_creature_card_to_regenerate(cards):
    from tests.test_rules_wave100n_multi import to_graveyard
    s = build(cards, ["Zombie Scavengers", "Grizzly Bears", "Llanowar Elves", "Forest"])
    zs = put(s, "Zombie Scavengers")
    to_graveyard(s, 1, "Grizzly Bears")
    to_graveyard(s, 1, "Forest")
    to_graveyard(s, 1, "Llanowar Elves")
    to_graveyard(s, 1, "Forest")
    from tests.test_rules_wave100f_control import ch
    ab = next(x for x in ch(s, zs).abilities if x.text.startswith("Exile the top"))
    act(s, "p1", type="activate_ability", card_id=zs.id, ability=ab.index)
    d = s.state.rules.decision
    bears, elves = (next(o.id for o in d.options if o.label == n) for n in ("Grizzly Bears", "Llanowar Elves"))
    with pytest.raises(ActionError):  # (404.2: the Bears are not the top creature card)
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[bears])
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[elves])
    answer(s)
    assert zone_of(s, "Llanowar Elves") == "p1:exile" and zone_of(s, "Grizzly Bears") == "p1:graveyard"
    assert s.state.rules.regen_shields.get(s.state.rules.object_id(zs.id)) == 1  # 701.19a: one shield
    check(s)


def test_toluz_exiles_discards_and_returns_them_when_it_dies(cards):
    s = build(cards, ["Toluz, Clever Conductor", "Grizzly Bears", "Grizzly Bears", "Rivals' Duel"], ["Test Giant 110F"])
    giant = put(s, "Test Giant 110F", "p2")
    bears = to_hand(s, "Grizzly Bears")
    mana(s, W=1, U=1, B=1)
    cast(s, "Toluz, Clever Conductor")
    answer(s, bears.id)  # (connive: draw, then discard the Bears)
    toluz = next(c for c in s.state.cards.values() if c.name.startswith("Toluz"))
    assert zone_of(s, "Grizzly Bears") == "p1:exile"  # (the discard trigger exiled it from the graveyard)
    mana(s, R=1, C=3)
    cast(s, "Rivals' Duel", [toluz.id, giant.id], target_counts=[2])  # (Toluz 3/1 dies fighting the 3/3 Giant)
    answer(s)
    assert zone_of(s, "Toluz, Clever Conductor") == "p1:graveyard"
    assert sorted(c.zone for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.zone != "p1:library") == ["p1:hand", "p1:hand"]
    check(s)
