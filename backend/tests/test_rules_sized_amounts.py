"""Damage (and life) sized by a count, a power or toughness, an event amount or X (wave 3D): the
wordings of real Commander cards, read through the values grammar (app/rules/values.py) and the
resolving ability's own context (608.2h: values are determined as the effect is carried out, from
last known information once the object has left; 107.3 X). Damage still goes through the damage
choke point (replace.py): a source's lifelink and deathtouch count (120.3f). Each scenario checks
that replaying the recorded history reproduces the table."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.rules import scripts
from app.rules.characteristics import Characteristics
from app.rules.oracle import parse_abilities
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, turn_on
from tests.test_rules_attachments import build, mana, named, to_hand, token
from tests.test_rules_combat import attack, automate, creature, table
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.test_rules_trigger_context import resolve_all

EXTRA = [
    card("Domri's Ambush", set_code="tst", number="DA1", mana_cost="{R}{G}", cmc=2.0, type_line="Instant",
         oracle_text="Put a +1/+1 counter on target creature you control. Then that creature deals damage equal to its "
                     "power to target creature or planeswalker you don't control.", colors=["R", "G"], color_identity=["R", "G"]),
    card("Polliwallop", set_code="tst", number="PW1", mana_cost="{3}{G}", cmc=4.0, type_line="Instant",
         oracle_text="This spell costs {3} less to cast if you control a Frog.\nTarget creature you control deals damage "
                     "equal to twice its power to target creature you don't control.", colors=["G"], color_identity=["G"]),
    card("Bartz and Boko", set_code="tst", number="BB1", mana_cost="{3}{G}{G}", cmc=5.0, type_line="Legendary Creature — Human Bird",
         oracle_text="Affinity for Birds (This spell costs {1} less to cast for each Bird you control.)\nWhen Bartz and Boko enters, "
                     "each other Bird you control deals damage equal to its power to target creature an opponent controls.",
         power="4", toughness="3", colors=["G"], color_identity=["G"]),
    card("Ingenious Artillerist", set_code="tst", number="IA1", mana_cost="{2}{R}", cmc=3.0, type_line="Creature — Human Artificer",
         oracle_text="Whenever one or more artifacts you control enter, this creature deals that much damage to each opponent.",
         power="3", toughness="1", colors=["R"], color_identity=["R"]),
    card("Chain Reaction", set_code="tst", number="CR1", mana_cost="{2}{R}{R}", cmc=4.0, type_line="Sorcery",
         oracle_text="Chain Reaction deals X damage to each creature, where X is the number of creatures on the battlefield.",
         colors=["R"], color_identity=["R"]),
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def life(s, pid="p1"):
    return s.state.players[pid].life


def pick(s, *ids):
    d = s.state.rules.decision
    assert d is not None, "no decision"
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(ids))
    pass_until_stack_empty(s)


def counters(s, card_, n):
    act(s, "p1", type="counter", card_ids=[card_.id], kind="+1/+1", delta=n)


def parse(text):
    ab = parse_abilities(text)[0]
    return scripts.definitions(Characteristics(name="Test", abilities=(ab,))).get(ab.index)


def make(s, text, pid="p1"):
    """An ability that creates a token creature: its entering is a real event (a token placed by hand isn't)."""
    src = token(s, pid, "Maker", "0/1", text=text)
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=src.id, ability=0)


# -- parsing: real cards' wordings ------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "Whenever a creature you control enters, it deals damage equal to its power to any target.",  # Warstorm Surge
    "Whenever another creature you control dies, it deals damage equal to its power to target player or planeswalker.",  # Stalking Vengeance
    "Whenever this creature or another Lhurgoyf creature you control enters, that creature deals damage equal to its power to any target.",
    "Whenever a Dragon you control enters, it deals X damage to any target, where X is the number of Dragons you control.",  # Dragon Tempest
    "Whenever equipped creature is dealt damage, it deals that much damage to any target.",  # Blazing Sunsteel
    "Whenever a commander you control deals combat damage to an opponent, it deals that much damage to each other opponent.",  # Kediss
    "Whenever you cast a noncreature spell, ~ deals damage equal to that spell's mana value to any target.",  # Thor
    "{R}, {T}, Sacrifice another creature: ~ deals damage equal to the sacrificed creature's power to target player or planeswalker.",  # Brion
    "{3}{R}, Sacrifice an artifact: ~ deals damage equal to the sacrificed artifact's mana value to any target.",  # Bosh
    "{R}, Sacrifice this creature: It deals damage equal to its power to target creature or planeswalker.",  # Heartfire Immolator
])
def test_real_card_wordings_are_automated(text):
    assert parse(text) is not None


@pytest.mark.parametrize("text", [
    # the sacrificed creature is read only from a cost's payment record: an effect's sacrifice, or no sacrifice at all, stays manual
    "Whenever this creature attacks, you may sacrifice another creature. When you do, ~ deals damage equal to the sacrificed creature's power to any target.",
    "{R}, {T}: ~ deals damage equal to the sacrificed creature's power to target player or planeswalker.",
    # "each other opponent" without an event naming one opponent
    "At the beginning of your upkeep, ~ deals 1 damage to each other opponent.",
])
def test_unfounded_references_stay_manual(text):
    assert parse(text) is None


# -- an event's object deals the damage (608.2h) ----------------------------------------------------
def test_entering_creature_deals_damage_equal_to_its_power(cards):
    s = build(cards)
    token(s, "p1", "Warstorm Surge", "0/4", text="Whenever a creature you control enters, it deals damage equal to its power to any target.")
    make(s, "{1}: Create a 4/3 red Ogre creature token.")
    pick(s, "p2")
    assert life(s, "p2") == 36
    replay_matches(s)


def test_dying_creature_deals_damage_equal_to_its_last_known_power(cards):
    s = build(cards)
    token(s, "p1", "Stalking Vengeance", "0/4",
          text="Whenever another creature you control dies, it deals damage equal to its power to target player or planeswalker.")
    victim = token(s, "p1", "Victim", "1/1", text="{1}: Sacrifice this creature.")
    counters(s, victim, 2)  # a 3/3 as it dies
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=victim.id, ability=0)
    pass_until_stack_empty(s)
    pick(s, "p2")
    assert victim.id not in s.state.cards and life(s, "p2") == 37
    replay_matches(s)


def test_event_creature_with_lifelink_gains_life_for_the_damage(cards):
    """120.3f: the creature that deals the damage is the source: its lifelink counts (702.15b)."""
    s = build(cards)
    token(s, "p1", "Warstorm Surge", "0/4", text="Whenever a creature you control enters, it deals damage equal to its power to any target.")
    make(s, "{1}: Create a 2/2 white Vampire creature token with lifelink.")
    pick(s, "p2")
    assert life(s, "p2") == 38 and life(s) == 42
    replay_matches(s)


def test_where_x_is_the_number_of_dragons(cards):
    s = build(cards)
    token(s, "p1", "Dragon Tempest", "0/4",
          text="Whenever a Dragon you control enters, it deals X damage to any target, where X is the number of Dragons you control.")
    maker = token(s, "p1", "Maker", "0/1", text="{1}: Create a 3/3 red Dragon creature token with flying.")
    for _ in range(2):
        mana(s, C=1)
        act(s, "p1", type="activate_ability", card_id=maker.id, ability=0)
        pick(s, "p2")
    assert life(s, "p2") == 40 - 1 - 2  # one Dragon, then two
    replay_matches(s)


def test_that_much_damage_to_the_creature_that_was_dealt_damage(cards):
    s = build(cards)
    sun = token(s, "p1", "Shield", "1/9", text="Whenever this creature is dealt damage, it deals that much damage to any target.")
    pinger = token(s, "p1", "Pinger", "1/1", text="{1}: This creature deals 3 damage to target creature.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=pinger.id, ability=0, targets=[sun.id])
    pass_until_stack_empty(s)
    pick(s, "p2")
    assert life(s, "p2") == 37
    replay_matches(s)


# -- "each other opponent": the opponents besides the one the event named (multiplayer) --------------
def test_each_other_opponent_takes_the_combat_damage_too(cards):
    s = table(cards, players=3)
    ham = creature(s, "p1", "Hydra Omnivore", "8/8",
                   "Whenever this creature deals combat damage to an opponent, it deals that much damage to each other opponent.")
    automate(s)
    attack(s, (ham, "p2"))
    resolve_all(s)
    assert life(s, "p2") == 32 and life(s, "p3") == 32 and life(s, "p1") == 40
    replay_matches(s)


# -- that spell's mana value ------------------------------------------------------------------------
def test_damage_equal_to_the_cast_spells_mana_value(cards):
    s = build(cards, "Murder")
    token(s, "p1", "Thor, God of Thunder", "4/4",
          text="Whenever you cast a noncreature spell, ~ deals damage equal to that spell's mana value to any target.")
    victim = token(s, "p2", "Goat", "1/1")
    spell = to_hand(s, "Murder")
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[victim.id])
    pick(s, "p2")
    assert life(s, "p2") == 37  # Murder's mana value is 3
    replay_matches(s)


# -- the sacrificed creature, as it last existed (cost: 608.2h) ----------------------------------------
def test_damage_equal_to_the_sacrificed_creatures_power(cards):
    s = table(cards)
    brion = creature(s, "p1", "Brion Stoutarm", "3/3",
                     "{R}, {T}, Sacrifice another creature: ~ deals damage equal to the sacrificed creature's power to target player or planeswalker.")
    fodder = creature(s, "p1", "Fodder", "1/1")
    counters(s, fodder, 3)  # a 4/4 as it is sacrificed
    turn_on(s)  # (what's already there isn't summoning sick)
    act(s, "p1", type="pass_priority")
    mana(s, R=1)
    act(s, "p1", type="activate_ability", card_id=brion.id, ability=0, targets=["p2"], cost_choices=[{"component": 2, "cards": [fodder.id]}])
    pass_until_stack_empty(s)
    assert fodder.id not in s.state.cards and s.state.players["p2"].life == 36
    replay_matches(s)


# -- an earlier instruction's target deals it (a bite), twice its power, counters first -----------------
def test_put_a_counter_then_that_creature_deals_damage_equal_to_its_power(cards):
    s = build(cards, "Domri's Ambush")
    mine = token(s, "p1", "Bear", "2/2")
    theirs = token(s, "p2", "Wall", "0/6")
    spell = to_hand(s, "Domri's Ambush")
    mana(s, R=1, G=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[mine.id, theirs.id], target_counts=[1, 1])
    pass_until_stack_empty(s)
    assert named(s, "Wall").damage == 3  # the counter was put first: a 3/3 deals 3 (608.2c, 608.2h)
    replay_matches(s)


def test_twice_its_power(cards):
    s = build(cards, "Polliwallop")
    mine = token(s, "p1", "Bear", "3/3")
    theirs = token(s, "p2", "Wall", "0/9")
    spell = to_hand(s, "Polliwallop")
    mana(s, G=1, C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[mine.id, theirs.id], target_counts=[1, 1])
    pass_until_stack_empty(s)
    assert named(s, "Wall").damage == 6
    replay_matches(s)


# -- X defined by the text (107.3) ------------------------------------------------------------------------
def test_x_is_the_number_of_creatures_on_the_battlefield(cards):
    s = build(cards, "Chain Reaction")
    a, b = token(s, "p1", "Bear", "2/2"), token(s, "p2", "Elk", "2/2")
    c = token(s, "p2", "Wall", "0/9")
    spell = to_hand(s, "Chain Reaction")
    mana(s, R=2, C=2)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    pass_until_stack_empty(s)
    assert a.id not in s.state.cards and b.id not in s.state.cards  # X is 3: the 2/2s die
    assert named(s, "Wall").damage == 3 and c.id in s.state.cards
    replay_matches(s)


# -- "each creature you control deals damage equal to its power": every one is a source ----------------------
def test_each_other_bird_deals_damage_equal_to_its_power(cards):
    s = build(cards, "Bartz and Boko")
    for name, pt in (("Crow", "2/2"), ("Hawk", "3/3")):
        p, tt = pt.split("/")
        act(s, "p1", type="create_token", player="p1", token={"name": name, "type_line": "Token Creature — Bird", "power": p, "toughness": tt})
    wall = token(s, "p2", "Wall", "0/9")
    bartz = to_hand(s, "Bartz and Boko")
    mana(s, G=2, C=3)
    act(s, "p1", type="cast_spell", card_id=bartz.id)
    pass_until_stack_empty(s)
    pick(s, wall.id)
    assert named(s, "Wall").damage == 5  # 2 + 3 (not Bartz: "each other Bird"), dealt at once
    replay_matches(s)


def test_each_source_with_lifelink_gains_life(cards):
    s = build(cards)
    keeper = token(s, "p1", "Keeper", "0/4",
                   text="{1}: Each creature you control deals damage equal to its power to target creature you don't control.")
    token(s, "p1", "Vampire", "2/2", text="Lifelink")
    wall = token(s, "p2", "Wall", "0/9")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=keeper.id, ability=0, targets=[wall.id])
    pass_until_stack_empty(s)
    assert named(s, "Wall").damage == 2 and life(s) == 42  # (the 0-power Keeper deals none)
    replay_matches(s)


# -- "that much" of a "one or more" event is how many of them (603.2c) -----------------------------------------
def test_one_or_more_artifacts_enter_deals_that_much(cards):
    s = build(cards, "Ingenious Artillerist")
    act(s, "p1", type="move", card_ids=[to_hand(s, "Ingenious Artillerist").id], to={"zone": "battlefield"})
    make(s, "{1}: Create two Treasure tokens.")
    pass_until_stack_empty(s)
    assert life(s, "p2") == 38  # one batch of two artifacts: 2 damage, once
    replay_matches(s)
