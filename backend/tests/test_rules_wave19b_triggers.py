"""Wave 19B: the trigger long tail, fourth pass (CR 2026-09-25). Real Oracle text; every scenario checks the replay and a save and a load.

* 608.2d: "its controller may draw a card" - the controller of the creature that dealt the damage decides.
* 701.17a: "mill four cards, then you may put a creature or land card from among the milled cards on top of your library", and
  "a creature card and/or a land card from among them into your hand" - the pick is from the cards the mill put into the graveyard.
* 701.54a: "if you chose a creature other than Gandalf as your Ring-bearer" - the creature this tempting chose.
* 903.8: "for each time you've cast a commander from the command zone this game" - the casts counted so far.
* 903.3: "your commander enters / attacks", "you attack with your commander" - a commander you own (not another player's).
* 603.10a / 400.7: "put that card onto the battlefield" for a sacrificed permanent, "put them onto the battlefield tapped" for the
  land cards a mill put into the graveyard - the trigger event's cards, found where they went.
* 508.1b: "deals 1 damage to the player or planeswalker it's attacking" - what the attacker the trigger is about attacks now.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act, zone
from tests.test_rules_conditionals import token_of
from tests.test_rules_wave5c_combat import build as combat_build
from tests.test_rules_wave5c_combat import declare, to_attack, to_blocks
from tests.test_rules_wave5c_combat import put as combat_put
from tests.test_rules_wave12a_counters_keywords import answer, real
from tests.test_rules_effects import mana
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
]

NAMES = [e["name"] for e in EXTRA if not e["name"].startswith("Probe")]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_hellrider_damages_what_each_attacker_attacks(cards):
    # 508.1b: one trigger per attacking creature; Carol is attacked by one of them, Bob by the other
    s = combat_build(cards, "Hellrider", players=3)
    combat_put(s, "Hellrider")
    a = token_of(s, "p1", "Ape", "Token Creature — Ape", "2/2", "Haste")
    b = token_of(s, "p1", "Bat", "Token Creature — Bat", "2/2", "Haste")
    to_attack(s)
    declare(s, (a, "p2"), (b, "p3"))
    to_blocks(s)
    assert (life(s, "p2"), life(s, "p3")) == (39, 39)
    check(s)


def test_scorch_spitter_damages_the_player_it_attacks(cards):
    s = combat_build(cards, "Scorch Spitter")
    spitter = combat_put(s, "Scorch Spitter")
    to_attack(s, 3)
    declare(s, (spitter, "p2"))
    to_blocks(s)
    assert life(s, "p2") == 39
    check(s)


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
