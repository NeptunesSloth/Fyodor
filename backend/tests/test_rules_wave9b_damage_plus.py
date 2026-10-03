"""Wave 9B: "it deals that much damage plus N instead" with several kinds of sources (Mechanized Warfare, Pyromancer's Gauntlet,
Valley Flamecaller) and a variable amount (Hawkeye, Young Avenger: plus X, Fated Firepower: plus the fire counters),
researched against CR 2026-09-25.

* 614.1a, 120.4b: a replacement effect on the damage event; 609.7c: a "source" is any object with the stated property
  (a red or artifact source; a Lizard, Mouse, Otter, or Raccoon; a red instant or sorcery spell or a red planeswalker).
* 608.2h: the added amount (a power, a number of counters) is read as the damage is dealt.

Every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.rules import coverage, replace_grammar
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana, pass_until_stack_empty
from tests.test_rules_wave4h_activation_costs import activate
from tests.test_rules_wave9b_exile_permission import build, find, put, roundtrip

EXTRA = [
    card("Pyromancer's Gauntlet", set_code='tst', number='D1', mana_cost='{5}', cmc=5.0, type_line='Artifact', oracle_text='If a red instant or sorcery spell you control or a red planeswalker you control would deal damage to a permanent or player, it deals that much damage plus 2 to that permanent or player instead.'),  # noqa: E501
    card('Mechanized Warfare', set_code='tst', number='D2', mana_cost='{1}{R}{R}', cmc=3.0, type_line='Enchantment', oracle_text='If a red or artifact source you control would deal damage to an opponent or a permanent an opponent controls, it deals that much damage plus 1 instead.', colors=['R'], color_identity=['R']),  # noqa: E501
    card('Valley Flamecaller', set_code='tst', number='D3', mana_cost='{2}{R}', cmc=3.0, type_line='Creature — Lizard Warlock', oracle_text='If a Lizard, Mouse, Otter, or Raccoon you control would deal damage to a permanent or player, it deals that much damage plus 1 instead.', power='3', toughness='3', colors=['R'], color_identity=['R']),  # noqa: E501
    card('Hawkeye, Young Avenger', set_code='tst', number='D4', mana_cost='{3}{R}', cmc=4.0, type_line='Legendary Creature — Human Archer Hero', oracle_text="Reach\nIf a source you control would deal noncombat damage to an opponent or a permanent an opponent controls, instead it deals that much damage plus X, where X is Hawkeye's power.", power='2', toughness='4', colors=['R'], color_identity=['R'], keywords=['Reach']),  # noqa: E501
    card('Fated Firepower', set_code='tst', number='D5', mana_cost='{X}{R}{R}{R}', cmc=3.0, type_line='Enchantment', oracle_text='Flash\nThis enchantment enters with X fire counters on it.\nIf a source you control would deal damage to an opponent or a permanent an opponent controls, it deals that much damage plus an amount of damage equal to the number of fire counters on this enchantment instead.', colors=['R'], color_identity=['R'], keywords=['Flash']),  # noqa: E501
]
NAMES = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_the_source_wordings_are_exact():
    src = replace_grammar._source
    assert src("a red or artifact source you control") == {
        "alts": [{"controller": "you", "colors": ["R"]}, {"controller": "you", "types": ["Artifact"]}]}
    assert src("a Lizard, Mouse, Otter, or Raccoon you control") == {
        "controller": "you", "subtypes": ["Lizard", "Mouse", "Otter", "Raccoon"]}
    alts = src("a red instant or sorcery spell you control or a red planeswalker you control")
    assert alts is not None and len(alts["alts"]) == 2 and alts["alts"][1] == {"controller": "you", "colors": ["R"], "types": ["Planeswalker"]}
    for text in ("a red or artifact and white source you control", "a red or or artifact source you control",
                 "a Lizard, or you control", "a red source you control or"):
        assert src(text) is None, text


def token(s, name, type_line, text="{R}: ~ deals 1 damage to target player."):
    act(s, "p1", type="create_token", player="p1", token={"name": name, "type_line": type_line, "power": "1", "toughness": "1", "text": text})
    return find(s, name)


def ping(s, tok):
    mana(s, R=1)
    activate(s, tok, "{R}: ", targets=["p2"])
    pass_until_stack_empty(s)


def life(s, pid="p2"):
    return s.state.players[pid].life


def test_mechanized_warfare_adds_one_for_a_red_or_artifact_source_you_control(cards):
    s = build(cards, p1=("Mechanized Warfare", "Lightning Bolt"))
    put(s, "Mechanized Warfare", "battlefield")
    plain = token(s, "Plain", "Token Creature — Test")
    artifact = token(s, "Gadget", "Token Artifact Creature — Construct")
    ping(s, plain)
    assert life(s) == 39  # colorless, not an artifact: no more
    ping(s, artifact)
    assert life(s) == 37  # an artifact source: 1 + 1
    bolt = put(s, "Lightning Bolt", "hand")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    pass_until_stack_empty(s)
    assert life(s) == 33  # a red source: 3 + 1
    roundtrip(s)


def test_pyromancers_gauntlet_adds_two_to_red_instants_only(cards):
    s = build(cards, p1=("Pyromancer's Gauntlet", "Lightning Bolt"))
    put(s, "Pyromancer's Gauntlet", "battlefield")
    plain = token(s, "Plain", "Token Creature — Test")
    ping(s, plain)
    assert life(s) == 39  # a creature's ability is neither a spell nor a planeswalker
    bolt = put(s, "Lightning Bolt", "hand")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    pass_until_stack_empty(s)
    assert life(s) == 34  # 3 + 2
    roundtrip(s)


def test_valley_flamecaller_adds_one_for_its_creature_types(cards):
    s = build(cards, p1=("Valley Flamecaller",))
    put(s, "Valley Flamecaller", "battlefield")
    goblin = token(s, "Imp", "Token Creature — Goblin")
    lizard = token(s, "Gecko", "Token Creature — Lizard")
    ping(s, goblin)
    assert life(s) == 39
    ping(s, lizard)
    assert life(s) == 37  # 1 + 1
    roundtrip(s)


def test_hawkeye_adds_his_power_to_noncombat_damage_only(cards):
    s = build(cards, p1=("Hawkeye, Young Avenger", "Lightning Bolt"))
    hawk = put(s, "Hawkeye, Young Avenger", "battlefield")
    bolt = put(s, "Lightning Bolt", "hand")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    pass_until_stack_empty(s)
    assert life(s) == 35  # 3 + Hawkeye's power 2
    act(s, "p1", type="counter", card_ids=[hawk.id], kind="+1/+1", delta=2)  # now a 4/6: the amount is read as the damage is dealt
    plain = token(s, "Plain", "Token Creature — Test")
    ping(s, plain)
    assert life(s) == 30  # 1 + 4
    roundtrip(s)


def test_fated_firepower_adds_its_fire_counters(cards):
    s = build(cards, p1=("Fated Firepower",))
    fire = put(s, "Fated Firepower", "battlefield")
    act(s, "p1", type="counter", card_ids=[fire.id], kind="fire", delta=3)
    plain = token(s, "Plain", "Token Creature — Test")
    ping(s, plain)
    assert life(s) == 36  # 1 + 3 fire counters
    act(s, "p1", type="counter", card_ids=[fire.id], kind="fire", delta=-3)
    ping(s, plain)
    assert life(s) == 35  # no counters left: 1
    roundtrip(s)
