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
* 115.4, 120.3: "deals 4 damage to another target battle or opponent and 1 damage to up to one target creature" (Invasion of Regatha); 614.1a: "plus 2 instead" to a creature, battle, or opponent.
* 508.1d, 509.1c: "Target creature attacks or blocks this turn if able."; 701.40g, 708.8: "You may turn a creature you control face up." (Hustle // Bustle).
* 701.20a, 202.2d: "Reveal any number of cards in your hand. You gain 2 life for each green mana symbol in those cards' mana costs." (Phosphorescent Feast).
* 602.5, 605.1a: "Creatures with flying can't attack or block, and their activated abilities with {T} in their costs can't be activated." (Katabatic Winds).
* 701.9a, 118.12: "Then discard two cards unless you discard an instant or sorcery card or a creature card with flying." (Steamcore Scholar).
* 709.5f, 709.5h: "unlock a locked door of up to one target Room you control" (Ghostly Keybearer).
* 508.3a, 508.5: "Whenever an opponent attacks a planeswalker you control with one or more creatures, ~ deals 2 damage to that player and you gain 2 life." (Oath of Kaya).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave18g_rooms import room
from tests.test_rules_wave34b_activated import activate, attack
from tests.test_rules_wave100f_attached import to_phase
from tests.test_rules_wave100f_gear import block
from tests.test_rules_wave100n_multi import EXTRA as _BASE
from tests.test_rules_wave100n_multi import (
    answer,
    card_db,  # noqa: F401  (fixture DB with EXTRA)
    cast,
    gy,
)
from tests.wave9c_kit import build, check, life, mana, put, to_hand, zone_of

EXTRA = [
    real('Oath of Kaya', '{1}{R}{W}', 3, 'Legendary Enchantment',
         "Whenever an opponent attacks a planeswalker you control with one or more creatures, Oath of Kaya deals 2 damage to that player and you gain 2 life.", None, 'RW'),
    real('Steamcore Scholar', '{2}{U}', 3, 'Creature — Weird Detective',
         "Flying, vigilance\nWhen this creature enters, draw two cards. Then discard two cards unless you discard an instant or sorcery card or a creature card with flying.",
         ('2', '2'), 'U'),
    real('Kaust, Eyes of the Glade', '{R/W}{G}', 2, 'Legendary Creature — Dryad Detective',
         "Whenever a creature you control that was turned face up this turn deals combat damage to a player, draw a card.\n{T}: Turn target face-down attacking creature you control face up.",
         ('2', '2'), 'GRW'),
    real('Ravager Wurm', '{3}{R}{G}{G}', 6, 'Creature — Wurm',
         "Riot (This creature enters with your choice of a +1/+1 counter or haste.)\nWhen this creature enters, choose up to one —\n• This creature fights target creature you don't control.\n• Destroy target land with an activated ability that isn't a mana ability.",
         ('4', '5'), 'RG'),
    real('Test Utility Land 110F', '', 0, 'Land', "{T}: Add {C}.\n{2}, {T}: Draw a card.", None, ''),
    real('Ghostly Keybearer', '{3}{U}', 4, 'Creature — Spirit',
         "Flying\nWhenever this creature deals combat damage to a player, unlock a locked door of up to one target Room you control.", ('3', '3'), 'U'),
    room("Grand Entryway", ("Grand Entryway", "{1}{W}", "When you unlock this door, create a 1/1 white Glimmer enchantment creature token."),
         ("Elegant Rotunda", "{2}{W}", "When you unlock this door, put a +1/+1 counter on each of up to two target creatures."), ["W"]),
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
    real('Invasion of Regatha', '{2}{R}', 3, 'Battle — Siege',
         "(As a Siege enters, choose an opponent to protect it. You and others can attack it. When it's defeated, exile it, then cast it transformed.)\nWhen this Siege enters, it deals 4 damage to another target battle or opponent and 1 damage to up to one target creature.", None, "R") | {"defense": "5"},
    real('Test Siege 110F', '{2}{R}', 3, 'Battle — Siege',
         "(As a Siege enters, choose an opponent to protect it. You and others can attack it. When it's defeated, exile it, then cast it transformed.)\nWhen this Siege enters, it deals 4 damage to another target battle or opponent and 1 damage to up to one target creature.", None, "R") | {"defense": "5"},
    real('Test Disciples 110F', '{1}{R}', 2, 'Creature — Human Monk',
         "If a noncreature source you control would deal damage to a creature, battle, or opponent, it deals that much damage plus 2 instead.", ('1', '1'), 'R'),
    real('Test Burn 110F', '{R}', 1, 'Instant', "Test Burn 110F deals 2 damage to target player.", None, 'R'),
    real('Hustle // Bustle', '{U/R} // {4}{R/G}{R/G}', 8, 'Instant // Sorcery',
         "Target creature attacks or blocks this turn if able.\n//\nCreatures you control get +2/+2 and gain trample until end of turn. You may turn a creature you control face up.", None, 'RGU')
    | {"layout": "split", "card_faces": [
        {"name": "Hustle", "mana_cost": "{U/R}", "type_line": "Instant", "oracle_text": "Target creature attacks or blocks this turn if able."},
        {"name": "Bustle", "mana_cost": "{4}{R/G}{R/G}", "type_line": "Sorcery",
         "oracle_text": "Creatures you control get +2/+2 and gain trample until end of turn. You may turn a creature you control face up."}]},
    real('Test Morpher 110F', '{2}{R}', 3, 'Creature — Goblin', 'Morph {R}', ('3', '2'), 'R'),
    real('Phosphorescent Feast', '{2}{G}{G}{G}', 5, 'Sorcery',
         "Chroma — Reveal any number of cards in your hand. You gain 2 life for each green mana symbol in those cards' mana costs.", None, 'G'),
    real('Test Hybrid 110F', '{G/W}{G/W}', 2, 'Creature — Elf', '', ('1', '1'), 'GW'),
    real('Test Flyer', '{2}{U}', 3, 'Creature — Bird', 'Flying\n{T}: Draw a card.', ('1', '1'), 'U'),
]
_BASE.extend(EXTRA)  # the shared fixture DB builder reads this list
NAMES = ["Kaust, Eyes of the Glade", "Ravager Wurm", "Steamcore Scholar", "Ghostly Keybearer", "Oath of Kaya", "Katabatic Winds", "Rivals' Duel", "Dead Ringers", "Cathedral Membrane", "Taunt", "Jabari's Influence", "Don & Leo, Problem Solvers", "Rapid Fire", "Time and Tide", "Abby, Merciless Soldier", "Zombie Scavengers", "Toluz, Clever Conductor", "Invasion of Regatha", "Test Disciples 110F", "Hustle // Bustle", "Phosphorescent Feast"]


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


def test_invasion_of_regatha_hits_an_opponent_and_a_creature_but_not_itself(cards):
    s = build(cards, ["Invasion of Regatha", "Test Siege 110F"], ["Grizzly Bears"])
    bear = put(s, "Grizzly Bears", "p2")
    mana(s, R=2, C=4)
    first = cast(s, "Invasion of Regatha")
    answer(s)  # (the target: the opponent, then the Bears)
    assert life(s, "p2") == 36 and s.state.cards[bear.id].damage == 1
    second = cast(s, "Test Siege 110F")
    for _ in range(30):  # (the protector choice first, then the trigger's targets)
        d = s.state.rules.decision
        if d is not None and first.id in {o.id for o in d.options}:
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    assert {o.id for o in d.options} == {"p2", first.id} and second.id not in {o.id for o in d.options}  # 115.4: "another" battle
    answer(s)
    assert life(s, "p2") == 32
    check(s)


@pytest.mark.parametrize("target,hit", [("p2", 4), ("p1", 2)])
def test_disciples_adds_two_to_noncreature_damage_to_an_opponent(cards, target, hit):
    """614.1a: only damage to a creature, a battle or an opponent gets the +2; you are none of those."""
    s = build(cards, ["Test Disciples 110F", "Test Burn 110F"])
    put(s, "Test Disciples 110F")
    mana(s, R=1)
    cast(s, "Test Burn 110F", [target])
    answer(s)
    assert life(s, target) == 40 - hit
    check(s)


def test_hustle_forces_its_target_to_attack_on_its_controllers_turn(cards):
    s = build(cards, ["Hustle // Bustle", "Grizzly Bears"])
    bear = put(s, "Grizzly Bears")
    to_phase(s, "main1", turn=3)
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Hustle // Bustle").id, face=0, targets=[bear.id])
    answer(s)
    to_phase(s, "declare_attackers")
    with pytest.raises(ActionError):
        act(s, "p1", type="declare_attackers", attackers=[])
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    check(s)


def test_hustle_forces_its_target_to_block_on_another_turn(cards):
    s = build(cards, ["Hustle // Bustle", "Test Giant 110F"], ["Grizzly Bears"])
    giant, bear = put(s, "Test Giant 110F"), put(s, "Grizzly Bears", "p2")
    to_phase(s, "main1", turn=3)
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Hustle // Bustle").id, face=0, targets=[bear.id])
    answer(s)
    attack(s, giant)
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_blockers", blocks=[])
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": bear.id, "attacker_id": giant.id}])
    check(s)


@pytest.mark.parametrize("turn_up", [True, False])
def test_bustle_pumps_and_may_turn_a_creature_face_up(cards, turn_up):
    s = build(cards, ["Hustle // Bustle", "Test Morpher 110F", "Grizzly Bears"])
    morph = to_hand(s, "Test Morpher 110F")
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=morph.id, face_down=True)
    answer(s)
    bear = put(s, "Grizzly Bears")
    assert s.state.cards[morph.id].face_down
    mana(s, R=2, G=2, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Hustle // Bustle").id, face=1)
    for _ in range(30):
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[morph.id] if turn_up else [])
    assert s.state.cards[morph.id].face_down is not turn_up
    from tests.test_rules_wave100f_control import ch
    assert ch(s, bear).pt == (4, 4) and "trample" in ch(s, bear).keywords
    check(s)


@pytest.mark.parametrize("reveal,gain", [(("Grizzly Bears", "Test Hybrid 110F", "Test Giant 110F"), 6), (("Test Giant 110F",), 0), ((), 0)])
def test_phosphorescent_feast_counts_green_symbols_of_the_revealed_cards(cards, reveal, gain):
    s = build(cards, ["Phosphorescent Feast", "Grizzly Bears", "Test Hybrid 110F", "Test Giant 110F"])
    hand = {n: to_hand(s, n) for n in ("Grizzly Bears", "Test Hybrid 110F", "Test Giant 110F")}
    mana(s, G=3, C=2)
    cast(s, "Phosphorescent Feast")
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {c.id for c in hand.values()}  # (the Feast itself is on the stack)
    answer(s, [hand[n].id for n in reveal])
    assert life(s) == 40 + gain
    assert all(c.id in s.state.zones["p1:hand"] for c in hand.values())  # (revealing moves nothing)
    check(s)


@pytest.mark.parametrize("case,p2_life,p1_life", [("one", 38, 42), ("two", 36, 44), ("player", 40, 40)])
def test_oath_of_kaya_triggers_once_per_planeswalker_attacked(cards, case, p2_life, p1_life):
    """508.3a: one trigger for each planeswalker you control that is attacked, none for an attack on you."""
    from tests.test_rules_conditionals import until
    from tests.test_rules_wave36a_trigger_words import loyal
    from tests.wave36a_kit import ready, to_turn_of

    s = build(cards, ["Oath of Kaya", "Gideon Jura", "Vivien, Champion of the Wilds"], ["Grizzly Bears", "Test Giant 110F"], forests=20, islands=20)
    put(s, "Oath of Kaya")
    gideon, vivien = loyal(s, "Gideon Jura"), loyal(s, "Vivien, Champion of the Wilds")
    bear, giant = put(s, "Grizzly Bears", "p2"), put(s, "Test Giant 110F", "p2")
    ready(s, "Grizzly Bears", "Test Giant 110F", pid="p2")
    to_turn_of(s, "p2")
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    targets = {"one": [gideon.id, gideon.id], "two": [gideon.id, vivien.id], "player": ["p1", "p1"]}[case]
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": c.id, "target": t} for c, t in zip((bear, giant), targets, strict=True)])
    until(s, lambda s: s.state.turn.phase == "main2")
    assert life(s, "p2") == p2_life
    assert life(s, "p1") == p1_life - (5 if case == "player" else 0)  # (the 2/2 Bears and 3/3 Giant hit you for 5 unblocked)
    check(s)


@pytest.mark.parametrize("cast_face,locked_left", [(0, 2), (1, 1)])
def test_ghostly_keybearer_unlocks_the_locked_door_of_your_room(cards, cast_face, locked_left):
    """709.5f: the one locked door gets unlocked; 709.5h: its "when you unlock this door" ability triggers."""
    s = build(cards, ["Ghostly Keybearer", "Grand Entryway // Elegant Rotunda"])
    key = put(s, "Ghostly Keybearer")
    room_card = to_hand(s, "Grand Entryway // Elegant Rotunda")
    mana(s, W=1, C=2)
    act(s, "p1", type="cast_spell", card_id=room_card.id, face=cast_face)
    answer(s)
    to_phase(s, "main1", turn=3)
    attack(s, key)
    answer(s)
    oid = s.state.rules.object_id(room_card.id)
    assert s.state.rules.unlocked[oid] == [1, 2]
    assert life(s, "p2") == (37 if cast_face == 0 else 36)  # (the right door's counter came before combat when it was the cast half)
    assert any(c.name == "Glimmer" for c in s.state.cards.values())  # (the left door's trigger: at the cast, or from the unlock)
    assert s.state.cards[key.id].counters.get("+1/+1", 0) == 1  # (the right door's trigger, from the cast or from the unlock)
    check(s)


@pytest.mark.parametrize("pay,discarded", [("Test Burn 110F", 1), ("Test Flyer", 1), (None, 2)])
def test_steamcore_scholar_discards_one_fitting_card_or_two_cards(cards, pay, discarded):
    """118.12: an instant, a sorcery or a creature card with flying pays; Grizzly Bears (no flying) doesn't; declining discards two cards."""
    s = build(cards, ["Steamcore Scholar", "Test Burn 110F", "Test Flyer", "Grizzly Bears"], forests=20)
    hand = {n: to_hand(s, n) for n in ("Test Burn 110F", "Test Flyer", "Grizzly Bears")}
    mana(s, U=1, C=2)
    cast(s, "Steamcore Scholar")
    while s.state.rules.decision is None:
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["pay" if pay else "decline"])
    d = s.state.rules.decision
    if pay:
        assert d is not None and {o.id for o in d.options} == {hand["Test Burn 110F"].id, hand["Test Flyer"].id}  # (not the Bears)
        answer(s, [hand[pay].id])
    else:
        answer(s, [hand["Grizzly Bears"].id, hand["Test Burn 110F"].id])
    assert gy(s) == discarded
    assert (s.state.cards[hand[pay].id].zone == "p1:graveyard") if pay else (s.state.cards[hand["Grizzly Bears"].id].zone == "p1:graveyard")
    check(s)


@pytest.mark.parametrize("mode", ["fight", "land"])
def test_ravager_wurm_fights_or_destroys_a_land_with_a_nonmana_ability(cards, mode):
    """602.1, 605.1a: only a land with an activated ability that isn't a mana ability can be chosen (not an Island, not a mana-only land)."""
    s = build(cards, ["Ravager Wurm"], ["Grizzly Bears", "Test Utility Land 110F"], forests=20)
    bear = put(s, "Grizzly Bears", "p2")
    utility = put(s, "Test Utility Land 110F", "p2")
    island = next(c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2")
    act(s, "p2", type="move", card_ids=[island.id], to={"player": "p2", "zone": "battlefield"})
    mana(s, R=1, G=2, C=3)
    cast(s, "Ravager Wurm")
    for _ in range(12):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.options[0].id == "0:0":
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["0:0" if mode == "fight" else "1:0"])
        elif {o.id for o in d.options} & {bear.id, utility.id, island.id}:
            assert {o.id for o in d.options} == ({bear.id} if mode == "fight" else {utility.id})
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])  # (riot)
    assert s.state.cards[bear.id].zone == ("p2:graveyard" if mode == "fight" else "p2:battlefield")
    assert s.state.cards[utility.id].zone == ("p2:battlefield" if mode == "fight" else "p2:graveyard")
    assert s.state.cards[island.id].zone == "p2:battlefield"
    check(s)


@pytest.mark.parametrize("turn_up", [True, False])
def test_kaust_draws_only_for_a_creature_turned_face_up_this_turn(cards, turn_up):
    """708.8: the creature is the same object after turning up, so it "was turned face up this turn"; its unturned partner doesn't count."""
    s = build(cards, ["Kaust, Eyes of the Glade", "Test Morpher 110F", "Grizzly Bears"], forests=20, islands=20)
    mana(s, C=3)
    morph = to_hand(s, "Test Morpher 110F")
    act(s, "p1", type="cast_spell", card_id=morph.id, face_down=True)
    answer(s)
    kaust, bear = put(s, "Kaust, Eyes of the Glade"), put(s, "Grizzly Bears")
    to_phase(s, "main1", turn=3)
    act(s, "p1", type="set_stops", own=["declare_attackers"], others=[], smart_pass=False)
    attack(s, morph, bear)
    if turn_up:
        activate(s, "p1", kaust, "Turn target", targets=[morph.id])
        answer(s)
        assert not s.state.cards[morph.id].face_down
    before = len(s.state.zones["p1:hand"])
    to_phase(s, "main2")
    assert len(s.state.zones["p1:hand"]) - before == (1 if turn_up else 0)
    assert life(s, "p2") == 40 - (3 + 2 if turn_up else 2 + 2)
    check(s)
