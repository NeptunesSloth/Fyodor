"""Review of wave 27A: "unless … has ~ deal N damage to them" (118.12a), "creature that blocked this turn" (509.1g, 400.7),
"a player has no cards in hand" (Lupine Prototype) and "Enchanted artifact is a creature with base power and toughness N/N" (613.1d, 613.4b)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import sba
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck
from tests.test_rules_combat import attack, automate, block, creature
from tests.test_rules_effects import mana
from tests.test_rules_replacements2 import FURNACE_OF_RATH, URZAS_ARMOR, permanent
from tests.test_rules_wave9b_exile_permission import answer, build, find, put, roundtrip
from tests.test_rules_wave27a_static_other import EXTRA as WAVE_EXTRA

EXTRA = [*WAVE_EXTRA,
         card('Dwarven Scorcher', set_code='tst', number='R01', mana_cost='{2}{R}', cmc=3.0, type_line='Creature — Dwarf', oracle_text="Sacrifice this creature: This creature deals 1 damage to target creature unless that creature's controller has this creature deal 2 damage to them.", power='2', toughness='1', colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
         card("Tezzeret's Touch", set_code='tst', number='R02', mana_cost='{1}{U}{R}', cmc=3.0, type_line='Enchantment — Aura', oracle_text="Enchant artifact\nEnchanted artifact is a creature with base power and toughness 5/5 in addition to its other types.\nWhen enchanted artifact is put into a graveyard, return that card to its owner's hand.", colors=['U', 'R'], color_identity=['U', 'R'], keywords=['Enchant']),  # noqa: E501
         card('Ensoul Artifact', set_code='tst', number='R03', mana_cost='{1}{U}', cmc=2.0, type_line='Enchantment — Aura', oracle_text="Enchant artifact\nEnchanted artifact is a creature with base power and toughness 5/5 in addition to its other types.", colors=['U'], color_identity=['U'], keywords=['Enchant']),  # noqa: E501
         card('Test Relic', set_code='tst', number='R04', mana_cost='{3}', cmc=3.0, type_line='Artifact', oracle_text='', colors=[], color_identity=[]),
         card('Test Thopter', set_code='tst', number='R05', mana_cost='{1}', cmc=1.0, type_line='Artifact Creature — Thopter', oracle_text='', power='1', toughness='1', colors=[], color_identity=[]),  # noqa: E501
         ]


def _table(cards, mine, theirs):
    """Alice and Bob, rules automation still off (``automate`` turns it on with no creature summoning sick)."""
    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in mine), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in theirs), (10, "Island")])
    return GameSession(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False), cards=cards)


def _ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def _pt(s, c):
    return sba.power(s.state.cards[c.id], _ch(s, c)), sba.toughness(s.state.cards[c.id], _ch(s, c))


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def _cast_blister(s):
    land = put(s, "Test Tower", "battlefield", pid="p2")
    put(s, "Lava Blister", "hand")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=find(s, "Lava Blister").id, targets=[land.id])
    for _ in range(5):
        if s.state.rules.decision is not None:
            return land
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no payment offered")


def test_the_damage_paid_goes_through_the_payers_616_1_choice(cards):
    # 616.1: Urza's Armor (prevent 1) and Furnace of Rath (double) both apply to the damage the payer has the spell deal to them,
    # and the payer orders them; the damage is never dealt raw because the payment can't pause (118.12: paid, whatever happens)
    s = build(cards, p1=("Lava Blister",), p2=("Test Tower",))
    permanent(s, "p2", "Urza's Armor", "Artifact", URZAS_ARMOR)
    permanent(s, "p1", "Furnace of Rath", "Enchantment", FURNACE_OF_RATH)
    land = _cast_blister(s)
    d = s.state.rules.decision
    assert d.player == "p2"
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["pay"])
    d = s.state.rules.decision
    assert d is not None and d.player == "p2" and d.kind == "confirm"
    prevent_first = "yes" if "Urza's Armor first" in {o.id: o.label for o in d.options}["yes"] else "no"
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[prevent_first])
    answer(s)
    assert s.state.players["p2"].life == 30 and s.state.cards[land.id].zone == "p2:battlefield"  # (6 - 1) x 2
    roundtrip(s)


def test_a_sacrificed_source_deals_the_damage_as_it_last_existed(cards):
    # Dwarven Scorcher is sacrificed to activate; the damage the payer chooses comes from it as it last existed (608.2h)
    s = build(cards, p1=("Dwarven Scorcher",))
    guard = creature(s, "p2", "Guard", "1/1")
    scorcher = put(s, "Dwarven Scorcher", "battlefield")
    act(s, "p1", type="activate_ability", card_id=scorcher.id, ability=0, targets=[guard.id])
    for _ in range(5):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d.player == "p2" and s.state.cards[scorcher.id].zone == "p1:graveyard"
    act(s, "p2", type="choose", decision_id=d.id, option_ids=["pay"])
    answer(s)
    assert s.state.players["p2"].life == 38 and s.state.cards[guard.id].zone == "p2:battlefield" and s.state.cards[guard.id].damage == 0
    roundtrip(s)


# -- "creature that blocked this turn" (509.1g, 400.7) ------------------------------------------------------------------------------
def test_a_blocker_that_left_and_came_back_is_a_new_object_that_never_blocked(cards):
    s = _table(cards, ["Sizzling Barrage"], ["Ambush Viper"])
    sneak = creature(s, "p1", "Sneak")
    guard = put(s, "Ambush Viper", "battlefield", pid="p2")
    put(s, "Sizzling Barrage", "hand")
    automate(s)
    attack(s, (sneak, "p2"))
    block(s, "p2", (guard, sneak))
    assert s.state.rules.turn_log.blockers  # (recorded, and kept by a save: roundtrip)
    roundtrip(s)
    act(s, "p2", type="move", card_ids=[guard.id], to={"player": "p2", "zone": "exile"})
    act(s, "p2", type="move", card_ids=[guard.id], to={"player": "p2", "zone": "battlefield"})
    mana(s, R=4)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=find(s, "Sizzling Barrage").id, targets=[guard.id])
    roundtrip(s)


# -- "can't attack or block unless a player has no cards in hand" (Lupine Prototype) ------------------------------------------------
def test_lupine_prototype_reads_every_hand_as_attackers_are_declared(cards):
    for empty in (False, True):
        s = _table(cards, ["Lupine Prototype"], [])
        wolf = put(s, "Lupine Prototype", "battlefield")
        for pid in ("p1", "p2"):  # both players hold a card
            act(s, pid, type="move", card_ids=list(s.state.zones[f"{pid}:library"])[:1], to={"player": pid, "zone": "hand"})
        if empty:  # Bob's hand is empty
            act(s, "p2", type="move", card_ids=list(s.state.zones["p2:hand"]), to={"player": "p2", "zone": "graveyard"})
        automate(s)
        if empty:
            attack(s, (wolf, "p2"))
            answer(s)
            assert s.state.players["p2"].life == 34  # (5/5, +1/+1 as it attacks)
        else:  # no creature can attack: the declare attackers step is skipped (508.8)
            assert s.state.turn.phase == "main2" and not s.state.cards[wolf.id].attacking
        roundtrip(s)


# -- "Enchanted artifact is a creature with base power and toughness N/N in addition to its other types" (613.1d, 613.4b) ------------
def test_tezzerets_touch_animates_and_returns_the_artifact_card_when_it_dies(cards):
    s = build(cards, p1=("Tezzeret's Touch", "Test Relic"))
    relic = put(s, "Test Relic", "battlefield")
    put(s, "Tezzeret's Touch", "hand")
    mana(s, U=1, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=find(s, "Tezzeret's Touch").id, targets=[relic.id])
    answer(s)
    assert _pt(s, relic) == (5, 5) and {"Artifact", "Creature"} <= _ch(s, relic).types
    breaker = permanent(s, "p1", "Breaker", "Artifact", "{1}: Destroy target artifact.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=breaker.id, ability=0, targets=[relic.id])
    answer(s)
    assert s.state.cards[relic.id].zone == "p1:hand"  # "return that card to its owner's hand"
    assert s.state.cards[find(s, "Tezzeret's Touch").id].zone == "p1:graveyard"
    roundtrip(s)


def test_ensoul_on_an_artifact_creature_sets_its_base_and_a_later_setter_wins(cards):
    # 613.4b: the base 5/5 replaces the printed 1/1 (layer 7b); a later "base power and toughness 1/1" applies after it (timestamp)
    # and +1/+1 counters still count (layer 7c); when the Aura leaves, the creature is no longer 5/5
    s = build(cards, p1=("Ensoul Artifact", "Test Thopter"))
    thopter = put(s, "Test Thopter", "battlefield")
    aura = put(s, "Ensoul Artifact", "battlefield")
    act(s, "p1", type="attach", card_ids=[aura.id], to=thopter.id)
    assert _pt(s, thopter) == (5, 5) and "Thopter" in _ch(s, thopter).subtypes
    act(s, "p1", type="counter", card_ids=[thopter.id], kind="+1/+1", delta=1)
    assert _pt(s, thopter) == (6, 6)
    shrinker = permanent(s, "p1", "Shrinker", "Artifact", "{1}: Target creature has base power and toughness 1/1 until end of turn.")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=shrinker.id, ability=0, targets=[thopter.id])
    answer(s)
    assert _pt(s, thopter) == (2, 2)
    act(s, "p1", type="move", card_ids=[aura.id], to={"player": "p1", "zone": "graveyard"})
    assert _pt(s, thopter) == (2, 2)
    roundtrip(s)


def test_ensoul_on_a_noncreature_artifact_under_march_of_the_machines(cards):
    # 613.8a: March applies to noncreature artifacts, Ensoul makes the artifact a creature: either way the base is 5/5 (Ensoul's
    # 7b setter is the later one, or March no longer applies to it); without the Aura, March makes it a 3/3
    s = build(cards, p1=("Ensoul Artifact", "Test Relic"))
    permanent(s, "p1", "March", "Enchantment", "Each noncreature artifact is an artifact creature with power and toughness each equal to its mana value.")
    relic = put(s, "Test Relic", "battlefield")
    assert _pt(s, relic) == (3, 3)
    aura = put(s, "Ensoul Artifact", "battlefield")
    act(s, "p1", type="attach", card_ids=[aura.id], to=relic.id)
    assert _pt(s, relic) == (5, 5)
    roundtrip(s)
