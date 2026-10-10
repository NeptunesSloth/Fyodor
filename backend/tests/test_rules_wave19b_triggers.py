"""Wave 19B: the trigger long tail, fourth pass (CR 2026-09-25). Real Oracle text; every scenario checks the replay and a save and a load.

* 608.2d: "its controller may draw a card" - the controller of the creature that dealt the damage decides.
* 701.17a: "mill four cards, then you may put a creature or land card from among the milled cards on top of your library", and
  "a creature card and/or a land card from among them into your hand" - the pick is from the cards the mill put into the graveyard.
* 701.54a: "if you chose a creature other than Gandalf as your Ring-bearer" - the creature this tempting chose.
* 903.8: "for each time you've cast a commander from the command zone this game" - the casts counted so far.
* 903.3: "your commander enters / attacks", "you attack with your commander" - a commander you own (not another player's).
* 603.10a / 400.7: "put that card onto the battlefield" for a sacrificed permanent, "put them onto the battlefield tapped" for the
  land cards a mill put into the graveyard - the trigger event's cards, found where they went.
* 701.3a: "attach up to one target Equipment you control to that creature" (the creature that entered), "attach target Equipment you
  control to up to one target creature you control".
* 701.16a: "investigate that many times" - one Clue for each point of damage / each counter the event counted.
* 508.5: "each creature defending player controls" (not targeted): the player the attacker was declared against, one player of three.
* 603.2e / 603.2: "becomes the target of a spell or ability an opponent controls, … that player" - the player whose spell or ability it was;
  "deals damage to an opponent, that opponent discards a card" - the opponent dealt damage.
* 608.2h / 601.1: "put any number of creature cards from your hand onto the battlefield", "an artifact card with mana value less than or
  equal to that damage" - chosen privately, not cast.
* 701.21a: "sacrifice any number of other permanents, then draw that many cards" - the player picks which (none is allowed).
* "deals 1 damage to the player or planeswalker it's attacking" stays manual (Hellrider-style damage after leaving combat is unsettled).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act, zone
from tests.test_rules_conditionals import through_combat, token_of
from tests.test_rules_effects import mana
from tests.test_rules_wave5c_combat import build as combat_build
from tests.test_rules_wave5c_combat import declare, to_attack, to_blocks
from tests.test_rules_wave5c_combat import put as combat_put
from tests.test_rules_wave12a_counters_keywords import answer, real
from tests.wave9c_kit import build, card_named, check, life, put, to_hand

EXTRA = [
    real('Hellrider', '{2}{R}{R}', 4, 'Creature — Devil', "Haste\nWhenever a creature you control attacks, this creature deals 1 damage to the player or planeswalker it's attacking.", ("3", "3"), 'R'),
    real('Scorch Spitter', '{1}{R}', 2, 'Creature — Lizard', "Whenever this creature attacks, it deals 1 damage to the player or planeswalker it's attacking.", ("2", "1"), 'R'),
    real('Edric, Spymaster of Trest', '{1}{G}{U}', 3, 'Legendary Creature — Elf Rogue', "Whenever a creature deals combat damage to one of your opponents, its controller may draw a card.", ("2", "2"), 'GU'),
    real('Synapse Sliver', '{3}{U}', 4, 'Creature — Sliver', "Whenever a Sliver deals combat damage to a player, its controller may draw a card.", ("1", "1"), 'U'),
    real('Lluwen, Imperfect Naturalist', '{B}{G}', 2, 'Legendary Creature — Elf Druid', "When Lluwen enters, mill four cards, then you may put a creature or land card from among the milled cards on top of your library.\n{2}{B/G}{B/G}, Discard a land card: Create a 1/1 black and green Worm creature token for each land card in your graveyard.", ("1", "3"), 'BG'),
    real('Sludge Titan', '{4}{B}{G}', 6, 'Creature — Phyrexian Zombie Giant', "Whenever this creature enters or attacks, mill five cards. You may put a creature card and/or a land card from among them into your hand.", ("5", "5"), 'BG'),
    real('Gandalf, Friend of the Shire', '{3}{U}', 4, 'Legendary Creature — Avatar Wizard', 'Flash\nYou may cast sorcery spells as though they had flash.\nWhenever the Ring tempts you, if you chose a creature other than Gandalf as your Ring-bearer, draw a card.', ("2", "4"), 'U'),
    real('Probe Temptation', '{1}', 1, 'Sorcery', 'The Ring tempts you.', None),
    real('Probe Soldier', '{1}{W}', 2, 'Creature — Human Soldier', '', ("1", "1"), 'W'),
    real('Jirina Kudro', '{1}{R}{W}{B}', 4, 'Legendary Creature — Human Soldier', "When Jirina Kudro enters, create a 1/1 white Human Soldier creature token for each time you've cast a commander from the command zone this game.\nOther Humans you control get +2/+0.", ("3", "3"), 'BRW'),
    real('We Ride at Dawn', '{2}{W}', 3, 'Enchantment', 'Legendary creature spells you cast have convoke. (Your creatures can help cast those spells. Each creature you tap while casting a legendary creature spell pays for {1} or one mana of that creature\'s color.)\nWhenever your commander attacks, create a 1/1 red Mercenary creature token with "{T}: Target creature you control gets +1/+0 until end of turn. Activate only as a sorcery."', None, 'W'),
    real('Nakia, Wakandan Operative', '{2}{G}', 3, 'Legendary Creature — Human Warrior Hero', 'Reach\nWhenever your commander enters, you become the monarch.\n{2}, {T}: Put two +1/+1 counters on target creature or Vehicle. Activate only as a sorcery.', ("3", "3"), 'G'),
    real('It That Betrays', '{12}', 12, 'Creature — Eldrazi', 'Annihilator 2 (Whenever this creature attacks, defending player sacrifices two permanents of their choice.)\nWhenever an opponent sacrifices a nontoken permanent, put that card onto the battlefield under your control.', ("11", "11"), ''),
    real('Hedge Shredder', '{2}{G}{G}', 4, 'Artifact — Vehicle', 'Whenever this Vehicle attacks, you may mill two cards.\nWhenever one or more land cards are put into your graveyard from your library, put them onto the battlefield tapped.\nCrew 1 (Tap any number of creatures you control with total power 1 or more: This Vehicle becomes an artifact creature until end of turn.)', ("5", "5"), 'G'),
    real('Probe Edict', '{B}', 1, 'Sorcery', 'Target opponent sacrifices a creature.', None, 'B'),
    real('Probe Mill', '{U}', 1, 'Sorcery', 'Target player mills three cards.', None, 'U'),
    real('Fecundity', '{2}{G}', 3, 'Enchantment', "Whenever a creature dies, that creature's controller may draw a card.", None, 'G'),
    real('Kemba, Kha Enduring', '{1}{W}', 2, 'Legendary Creature — Cat Cleric', 'Whenever Kemba or another Cat you control enters, attach up to one target Equipment you control to that creature.\nEquipped creatures you control get +1/+1.\n{3}{W}{W}: Create a 2/2 white Cat creature token.', ("2", "2"), 'W'),
    real('Iron Hills Stalwart', '{4}{R}', 5, 'Creature — Dwarf Warrior', 'Reach, trample\nWhen this creature enters, attach target Equipment you control to up to one target creature you control.', ("4", "5"), 'R'),
    real('Probe Blade', '{1}', 1, 'Artifact — Equipment', 'Equipped creature gets +1/+1.\nEquip {1}', None),
    real('Piper Wright, Publick Reporter', '{1}{U}', 2, 'Legendary Creature — Human Detective', 'Whenever Piper Wright deals combat damage to a player, investigate that many times. (To investigate, create a Clue token. It\'s an artifact with "{2}, Sacrifice this token: Draw a card.")\nWhenever you sacrifice a Clue, put a +1/+1 counter on target creature you control.', ("1", "2"), 'U'),
    real('Lonis, Genetics Expert', '{1}{G/U}{G/U}', 3, 'Legendary Creature — Snake Elf Detective', 'Evolve (Whenever a creature you control enters, if that creature has greater power or toughness than this creature, put a +1/+1 counter on this creature.)\nWhenever one or more +1/+1 counters are put on Lonis, investigate that many times.\nWhenever you sacrifice a Clue, put a +1/+1 counter on another target creature you control.', ("1", "2"), 'GU'),
    real('Swathcutter Giant', '{4}{R}{W}', 6, 'Creature — Giant Soldier', 'Vigilance\nWhenever this creature attacks, it deals 1 damage to each creature defending player controls.', ("5", "5"), 'RW'),
    real('Jangling Automaton', '{3}', 3, 'Artifact Creature — Construct', 'Whenever this creature attacks, untap all creatures defending player controls.', ("3", "2"), ''),
    real('Thunderbreak Regent', '{2}{R}{R}', 4, 'Creature — Dragon', 'Flying\nWhenever a Dragon you control becomes the target of a spell or ability an opponent controls, this creature deals 3 damage to that player.', ("4", "4"), 'R'),
    real('Zhang Liao, Hero of Hefei', '{4}{B}{B}', 6, 'Legendary Creature — Human Soldier', 'Whenever Zhang Liao deals damage to an opponent, that opponent discards a card.', ("3", "3"), 'B'),
    real('Probe Burst', '{R}', 1, 'Instant', 'Probe Burst deals 1 damage to any target.', None, 'R'),
    real('Ghalta, Stampede Tyrant', '{5}{G}{G}{G}', 8, 'Legendary Creature — Elder Dinosaur', 'Trample\nWhen Ghalta enters, put any number of creature cards from your hand onto the battlefield.', ("12", "12"), 'G'),
    real('Covert Technician', '{2}{U}', 3, 'Artifact Creature — Human Ninja', 'Ninjutsu {1}{U} ({1}{U}, Return an unblocked attacker you control to hand: Put this card onto the battlefield from your hand tapped and attacking.)\nWhenever this creature deals combat damage to a player, you may put an artifact card with mana value less than or equal to that damage from your hand onto the battlefield.', ("2", "4"), 'U'),
    real('Probe Rock', '{3}', 3, 'Artifact', '', None),
    real('Probe Giant', '{5}', 5, 'Creature — Giant', '', ("5", "5")),
    real('God-Eternal Bontu', '{3}{B}{B}', 5, 'Legendary Creature — Zombie God', "Menace\nWhen God-Eternal Bontu enters, sacrifice any number of other permanents, then draw that many cards.\nWhen God-Eternal Bontu dies or is put into exile from the battlefield, you may put her into her owner's library third from the top.", ("5", "6"), 'B'),
    real('Lord of Shatterskull Pass', '{3}{R}', 4, 'Creature — Minotaur Shaman', 'Level up {1}{R} ({1}{R}: Put a level counter on this. Level up only as a sorcery.)\nLEVEL 1-5\n6/6\nLEVEL 6+\n6/6\nWhenever this creature attacks, it deals 6 damage to each creature defending player controls.', ("3", "3"), 'R'),
    real('Font of Magic', '{3}{U}', 4, 'Enchantment', "Instant and sorcery spells you cast cost {1} less to cast for each time you've cast a commander from the command zone this game.", None, 'U'),
    real('Probe Divination', '{2}{U}', 3, 'Sorcery', 'You gain 1 life.', None, 'U'),
    real('Renounce', '{1}{W}', 2, 'Instant', 'Sacrifice any number of permanents. You gain 2 life for each permanent sacrificed this way.', None, 'W'),
]

NAMES = [e["name"] for e in EXTRA if not e["name"].startswith("Probe") and e["name"] not in ("Hellrider", "Scorch Spitter")]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_that_many_after_sacrificing_any_number_stays_manual(cards):
    # Scapeshift: "up to that many" is the number of lands sacrificed, not an event's amount - not read (wrong automation otherwise)
    from tests.fixtures.cards import card

    scape = card("Scapeshift", set_code="tst", number="19B1", mana_cost="{2}{G}{G}", cmc=4.0, type_line="Sorcery", colors=["G"],
                 color_identity=["G"], keywords=[], oracle_text="Sacrifice any number of lands. Search your library for up to that many land cards, put them onto the battlefield tapped, then shuffle.")
    assert coverage.of_card_data(scape).level != "FULL"


def test_damage_to_what_it_is_attacking_stays_manual(cards):
    # Review 19: "the player or planeswalker it's attacking" after the attacker left combat is an unsettled ruling
    # (docs/CURRENT_STATE.md: Hellrider-style damage stays manual)
    for name in ("Hellrider", "Scorch Spitter"):
        assert coverage.of_card_data(cards.resolve(name)).level != "FULL"


@pytest.mark.parametrize("name, kind", [("Edric, Spymaster of Trest", "Rogue"), ("Synapse Sliver", "Sliver")])
def test_its_controller_may_draw_on_combat_damage(cards, name, kind):
    # 608.2d: Alice's creature hits Bob; its controller (Alice) is asked and draws; declining draws nothing
    for take, drawn in (("yes", 1), ("no", 0)):
        s = combat_build(cards, name)
        combat_put(s, name)
        a = token_of(s, "p1", "Ape", f"Token Creature — {kind}", "2/2", "Haste")
        to_attack(s)
        declare(s, (a, "p2"))
        hand = len(zone(s.state, "p1", "hand"))
        for _ in range(40):
            d = s.state.rules.decision
            if d is not None and d.kind == "declare_blockers":
                act(s, d.player, type="declare_blockers", blocks=[])
            elif d is not None:
                assert d.player == "p1" and d.kind == "confirm"
                act(s, d.player, type="choose", decision_id=d.id, option_ids=[take])
            elif s.state.zones.get("stack"):
                act(s, s.state.rules.priority, type="pass_priority")
            elif s.state.turn.phase == "main2":
                break
            else:
                act(s, s.state.rules.priority, type="pass_priority")
        assert len(zone(s.state, "p1", "hand")) == hand + drawn
        check(s)


def cast(s, name, pid="p1", **m):
    spell = to_hand(s, name, pid)
    mana(s, pid, **m)
    act(s, pid, type="cast_spell", card_id=spell.id)


def test_mill_then_put_one_of_the_milled_cards_on_top_of_the_library(cards):
    s = combat_build(cards, "Lluwen, Imperfect Naturalist")
    cast(s, "Lluwen, Imperfect Naturalist", B=1, G=1)
    answer(s)  # the first milled land goes back on top
    top = s.state.zones["p1:library"][0]
    assert s.state.cards[top].name == "Forest"
    assert len(s.state.zones["p1:graveyard"]) == 3  # four milled, one put back
    check(s)


def test_mill_then_put_a_creature_and_a_land_into_the_hand(cards):
    s = combat_build(cards, "Sludge Titan")
    cast(s, "Sludge Titan", B=1, G=1, C=4)
    hand = len(zone(s.state, "p1", "hand"))
    answer(s)
    assert len(zone(s.state, "p1", "hand")) == hand + 1  # five Forests milled: one land (a creature and a land are two kinds)
    assert len(s.state.zones["p1:graveyard"]) == 4
    check(s)


@pytest.mark.parametrize("chosen, drawn", [("Probe Soldier", 1), ("Gandalf, Friend of the Shire", 0)])
def test_ring_bearer_other_than_the_source_draws(cards, chosen, drawn):
    s = combat_build(cards, "Gandalf, Friend of the Shire", "Probe Soldier", "Probe Temptation")
    combat_put(s, "Gandalf, Friend of the Shire")
    soldier = combat_put(s, "Probe Soldier")
    cast(s, "Probe Temptation", C=1)
    pick = soldier.id if chosen == "Probe Soldier" else next(c.id for c in s.state.cards.values() if c.name == chosen)
    hand = len(zone(s.state, "p1", "hand"))
    answer(s, pick)
    assert len(zone(s.state, "p1", "hand")) == hand + drawn
    check(s)


def test_tokens_for_each_commander_cast_from_the_command_zone(cards):
    s = combat_build(cards, "Jirina Kudro")
    krenko = next(c for c in s.state.cards.values() if c.name == "Krenko, Mob Boss" and c.owner == "p1")
    mana(s, "p1", R=2, C=2)
    act(s, "p1", type="cast_spell", card_id=krenko.id)  # the commander: one cast from the command zone
    answer(s)
    cast(s, "Jirina Kudro", C=1, R=1, W=1, B=1)
    answer(s)
    assert sum(1 for c in s.state.cards.values() if c.name == "Human Soldier" and c.zone == "p1:battlefield") == 1
    check(s)


def test_your_commander_enters_makes_you_the_monarch(cards):
    s = combat_build(cards, "Nakia, Wakandan Operative")
    combat_put(s, "Nakia, Wakandan Operative")
    krenko = next(c for c in s.state.cards.values() if c.name == "Krenko, Mob Boss" and c.owner == "p1")
    mana(s, "p1", R=2, C=2)
    act(s, "p1", type="cast_spell", card_id=krenko.id)
    answer(s)
    assert s.state.table.monarch == "p1"
    check(s)


def test_your_commander_attacks_makes_a_token(cards):
    s = combat_build(cards, "We Ride at Dawn")
    combat_put(s, "We Ride at Dawn")
    krenko = combat_put(s, "Krenko, Mob Boss")
    to_attack(s, 3)
    declare(s, (krenko, "p2"))
    to_blocks(s)
    assert sum(1 for c in s.state.cards.values() if c.name == "Mercenary" and c.zone == "p1:battlefield") == 1
    check(s)


def test_your_commander_attacking_under_an_opponents_control_still_triggers(cards):
    # Review 19: 903.3 "your commander" is the card your deck names, whoever controls it now (903.3d is only "control")
    s = combat_build(cards, "We Ride at Dawn")
    combat_put(s, "We Ride at Dawn")
    krenko = next(c for c in s.state.cards.values() if c.name == "Krenko, Mob Boss" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"player": "p2", "zone": "battlefield"})
    assert s.state.cards[krenko.id].controller == "p2"
    s.state.rules.controlled_since[krenko.id].turn = 0
    to_attack(s, 2)
    declare(s, (krenko, "p1"), pid="p2")
    to_blocks(s)
    assert sum(1 for c in s.state.cards.values() if c.name == "Mercenary" and c.zone == "p1:battlefield") == 1
    check(s)


def test_sacrificed_nontoken_permanent_comes_back_under_your_control(cards):
    s = build(cards, ["It That Betrays", "Probe Edict"], ["Probe Soldier"])
    put(s, "It That Betrays")
    soldier = put(s, "Probe Soldier", "p2")
    cast(s, "Probe Edict", B=1)
    answer(s, "p2")
    answer(s)
    assert s.state.cards[soldier.id].zone == "p1:battlefield" and s.state.cards[soldier.id].controller == "p1"
    check(s)


def test_lands_milled_into_the_graveyard_enter_tapped(cards):
    s = build(cards, ["Hedge Shredder", "Probe Mill"], [])
    put(s, "Hedge Shredder")
    cast(s, "Probe Mill", U=1)
    answer(s, "p1")
    answer(s)
    forests = [c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:battlefield"]
    assert len(forests) == 3 and all(c.tapped for c in forests)
    assert not [c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:graveyard"]
    check(s)


@pytest.mark.parametrize("take, drawn", [("yes", 1), ("no", 0)])
def test_the_dead_creatures_controller_is_the_one_asked_to_draw(cards, take, drawn):
    s = build(cards, ["Fecundity", "Probe Edict"], ["Probe Soldier"])
    put(s, "Fecundity")
    put(s, "Probe Soldier", "p2")
    cast(s, "Probe Edict", B=1)
    hand = len(zone(s.state, "p2", "hand"))
    seen = []
    for _ in range(10):  # the target, then Bob's own choice: whoever is asked
        d = s.state.rules.decision
        if d is None and not s.state.zones.get("stack"):
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        seen.append((d.player, d.kind))
        act(s, d.player, type="choose", decision_id=d.id, option_ids=["p2"] if d.kind != "confirm" else [take])
    assert ("p2", "confirm") in seen
    assert len(zone(s.state, "p2", "hand")) == hand + drawn
    check(s)


def test_equipment_attaches_to_the_cat_that_entered(cards):
    s = build(cards, ["Kemba, Kha Enduring", "Probe Blade"], [])
    blade = put(s, "Probe Blade")
    cast(s, "Kemba, Kha Enduring", W=1, C=1)
    answer(s, blade.id)
    kemba = card_named(s, "Kemba, Kha Enduring")
    assert s.state.cards[blade.id].attached_to == kemba.id
    check(s)


def test_equipment_attaches_to_up_to_one_target_creature(cards):
    s = build(cards, ["Iron Hills Stalwart", "Probe Blade", "Probe Soldier"], [])
    blade = put(s, "Probe Blade")
    soldier = put(s, "Probe Soldier")
    cast(s, "Iron Hills Stalwart", R=1, C=4)
    answer(s, blade.id, soldier.id)
    assert s.state.cards[blade.id].attached_to == soldier.id
    check(s)


def clues(s):
    return sum(1 for c in s.state.cards.values() if c.name == "Clue" and c.zone == "p1:battlefield")


def test_investigate_as_many_times_as_damage_dealt(cards):
    s = combat_build(cards, "Piper Wright, Publick Reporter")
    piper = combat_put(s, "Piper Wright, Publick Reporter")
    act(s, "p1", type="counter", card_ids=[piper.id], kind="+1/+1", delta=2)  # 3 power
    to_attack(s, 3)
    declare(s, (piper, "p2"))
    through_combat(s)
    assert clues(s) == 3
    check(s)


def test_creatures_of_the_defending_player_only_are_damaged(cards):
    s = combat_build(cards, "Swathcutter Giant", players=3)
    giant = combat_put(s, "Swathcutter Giant")
    walls = {pid: next(c for c in s.state.cards.values() if c.name == f"Wall {pid}") for pid in ("p2", "p3")}
    to_attack(s, 4)  # (the fourth turn is Alice's again with three players)
    declare(s, (giant, "p3"))
    to_blocks(s)
    assert (s.state.cards[walls["p2"].id].damage, s.state.cards[walls["p3"].id].damage) == (0, 1)
    check(s)


def test_creatures_of_the_defending_player_untap(cards):
    s = combat_build(cards, "Jangling Automaton", players=3)
    automaton = combat_put(s, "Jangling Automaton")
    walls = {pid: next(c for c in s.state.cards.values() if c.name == f"Wall {pid}") for pid in ("p2", "p3")}
    to_attack(s, 4)
    for w in walls.values():
        act(s, "p1", type="tap", card_ids=[w.id])
    declare(s, (automaton, "p2"))
    to_blocks(s)
    assert (s.state.cards[walls["p2"].id].tapped, s.state.cards[walls["p3"].id].tapped) == (False, True)
    check(s)


def test_the_player_who_targeted_the_dragon_is_dealt_3(cards):
    s = build(cards, ["Thunderbreak Regent", "Probe Burst"], ["Probe Burst"])
    regent = put(s, "Thunderbreak Regent")
    mine, theirs = to_hand(s, "Probe Burst"), to_hand(s, "Probe Burst", "p2")
    mana(s, "p1", R=1)
    mana(s, "p2", R=1)
    act(s, "p1", type="cast_spell", card_id=mine.id, targets=["p2"])  # Alice's own spell on Bob: not an opponent's targeting of her Dragon
    act(s, "p2", type="cast_spell", card_id=theirs.id, targets=[regent.id])  # Bob responds, targeting the Dragon
    answer(s)
    assert life(s, "p2") == 40 - 1 - 3 and life(s, "p1") == 40
    check(s)


def test_any_number_of_creature_cards_from_the_hand_enter(cards):
    s = build(cards, ["Ghalta, Stampede Tyrant", "Probe Soldier", "Probe Giant", "Probe Rock"], [])
    soldier, giant, rock = (to_hand(s, n) for n in ("Probe Soldier", "Probe Giant", "Probe Rock"))
    cast(s, "Ghalta, Stampede Tyrant", G=3, C=5)
    d = s.state.rules.decision
    assert d is not None and rock.id not in [o.id for o in d.options]  # (only creature cards are offered)
    answer(s, [soldier.id, giant.id])
    assert {s.state.cards[c.id].zone for c in (soldier, giant)} == {"p1:battlefield"} and s.state.cards[rock.id].zone == "p1:hand"
    check(s)


def test_artifact_with_mana_value_up_to_the_damage_dealt(cards):
    s = combat_build(cards, "Covert Technician", "Probe Blade", "Probe Rock")
    tech = combat_put(s, "Covert Technician")
    blade, rock = (to_hand(s, n) for n in ("Probe Blade", "Probe Rock"))
    to_attack(s, 3)
    declare(s, (tech, "p2"))
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None and d.kind == "confirm":  # (603.5: the "you may" is asked as the ability resolves)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"])
        elif d is not None:
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.kind == "choose_cards" and [o.id for o in d.options] == [blade.id]  # 2 damage: the 3-mana Rock is no option
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[blade.id])
    answer(s)
    assert s.state.cards[blade.id].zone == "p1:battlefield" and s.state.cards[rock.id].zone == "p1:hand"
    check(s)


@pytest.mark.parametrize("count", [2, 0])
def test_sacrifice_any_number_of_other_permanents_then_draw_that_many(cards, count):
    s = build(cards, ["God-Eternal Bontu", "Probe Rock", "Probe Blade"], [])
    rock, blade = put(s, "Probe Rock"), put(s, "Probe Blade")
    cast(s, "God-Eternal Bontu", B=2, C=3)
    d = s.state.rules.decision
    assert d is not None and d.min_choices == 0 and {o.id for o in d.options} == {rock.id, blade.id}  # (not Bontu herself)
    hand = len(zone(s.state, "p1", "hand"))
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[rock.id, blade.id][:count])
    answer(s)
    assert len(zone(s.state, "p1", "hand")) == hand + count
    assert (s.state.cards[rock.id].zone == "p1:graveyard") == (count == 2)
    check(s)


def test_leveled_up_creature_hits_only_the_defending_players_creatures(cards):
    # the grant at LEVEL 6+ is a quoted trigger: the same "each creature defending player controls" (508.5), one defender of three
    s = combat_build(cards, "Lord of Shatterskull Pass", players=3)
    lord = combat_put(s, "Lord of Shatterskull Pass")
    act(s, "p1", type="counter", card_ids=[lord.id], kind="level", delta=6)
    walls = {pid: next(c for c in s.state.cards.values() if c.name == f"Wall {pid}") for pid in ("p2", "p3")}
    to_attack(s, 4)
    declare(s, (lord, "p2"))
    to_blocks(s)
    assert walls["p2"].id not in s.state.cards and s.state.cards[walls["p3"].id].zone == "p3:battlefield"  # (a token dies: gone)
    check(s)


def test_spells_cost_less_for_each_commander_cast_from_the_command_zone(cards):
    s = build(cards, ["Font of Magic", "Probe Divination"], [])
    put(s, "Font of Magic")
    krenko = next(c for c in s.state.cards.values() if c.name == "Krenko, Mob Boss" and c.owner == "p1")
    mana(s, "p1", R=2, C=2)
    act(s, "p1", type="cast_spell", card_id=krenko.id)  # one cast from the command zone
    answer(s)
    cast(s, "Probe Divination", U=1, C=1)  # {2}{U} less {1}: only two mana are in the pool
    assert life(s, "p1") == 41
    check(s)


def test_renounce_gains_2_life_for_each_permanent_sacrificed_this_way(cards):
    s = build(cards, ["Renounce", "Probe Rock", "Probe Blade"], [])
    rock, blade = put(s, "Probe Rock"), put(s, "Probe Blade")
    cast(s, "Renounce", W=1, C=1)
    d = s.state.rules.decision
    assert d is not None and d.min_choices == 0
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[rock.id, blade.id])
    answer(s)
    assert life(s, "p1") == 44 and s.state.cards[rock.id].zone == "p1:graveyard"
    check(s)
