"""Wave 20A: attached events (Auras and Equipment), real Oracle text; every scenario checks the replay and a save/load round trip.

* 613.1d-f / 613.4b: "Enchanted creature is a Citizen with base power and toughness 1/1. It has defender and loses all other abilities."
* 702.11b: "Enchanted creature can't be the target of spells or abilities your opponents control." is hexproof.
* 613.4c: "+X/+X, where X is its mana value" (the equipped creature's); "+1/+0 for each instant and sorcery card in your graveyard".
* 205.4a: "Enchanted land is snow."  702.116a: "Equipped creature has myriad."
* 608.2c / 122.1: "put a +1/+1 counter on it. Then if it has three or more +1/+1 counters on it, sacrifice this Aura." (the Ordeals)
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle, token_of, until
from tests.test_rules_wave6c_tokens_pumps import build, chars, pt, put
from tests.test_rules_wave6e_statics import attack_with
from tests.test_rules_wave15e_keywords import build3, check, next_own_turn

EXTRA = [
    card('Spider-Man No More', set_code='tst', number='20A01', mana_cost='{1}{U}', cmc=2.0, type_line='Enchantment — Aura', oracle_text='Enchant creature\nEnchanted creature is a Citizen with base power and toughness 1/1. It has defender and loses all other abilities. (It also loses all other creature types.)', colors=['U'], color_identity=['U'], keywords=['Enchant']),  # noqa: E501
    card('Retro-Mutation', set_code='tst', number='20A02', mana_cost='{2}{U}', cmc=3.0, type_line='Enchantment — Aura', oracle_text="Flash\nEnchant creature\nEnchanted creature is a Turtle with base power and toughness 0/1. It can't attack and loses all abilities. (It also loses all other creature types.)", colors=['U'], color_identity=['U'], keywords=['Flash', 'Enchant']),  # noqa: E501
    card('Canopy Cover', set_code='tst', number='20A03', mana_cost='{1}{G}', cmc=2.0, type_line='Enchantment — Aura', oracle_text="Enchant creature\nEnchanted creature can't be blocked except by creatures with flying or reach.\nEnchanted creature can't be the target of spells or abilities your opponents control.", colors=['G'], color_identity=['G'], keywords=['Enchant']),  # noqa: E501
    card('Glamdring', set_code='tst', number='20A04', mana_cost='{2}', cmc=2.0, type_line='Legendary Artifact — Equipment', oracle_text='Equipped creature has first strike and gets +1/+0 for each instant and sorcery card in your graveyard.\nWhenever equipped creature deals combat damage to a player, you may cast an instant or sorcery spell from your hand with mana value less than or equal to that damage without paying its mana cost.\nEquip {3}', keywords=['Equip']),  # noqa: E501
    card('Hedron Matrix', set_code='tst', number='20A05', mana_cost='{4}', cmc=4.0, type_line='Artifact — Equipment', oracle_text='Equipped creature gets +X/+X, where X is its mana value.\nEquip {4}', keywords=['Equip']),  # noqa: E501
    card('Blade of Selves', set_code='tst', number='20A06', mana_cost='{2}', cmc=2.0, type_line='Artifact — Equipment', oracle_text="Equipped creature has myriad. (Whenever it attacks, for each opponent other than defending player, you may create a token copy that's tapped and attacking that player or a planeswalker they control. Exile the tokens at end of combat.)\nEquip {4}", keywords=['Equip']),  # noqa: E501
    card('Glittering Frost', set_code='tst', number='20A07', mana_cost='{2}{G}', cmc=3.0, type_line='Snow Enchantment — Aura', oracle_text='Enchant land\nEnchanted land is snow.\nWhenever enchanted land is tapped for mana, its controller adds an additional one mana of any color.', colors=['G'], color_identity=['G'], keywords=['Enchant']),  # noqa: E501
    card('Ordeal of Thassa', set_code='tst', number='20A08', mana_cost='{1}{U}', cmc=2.0, type_line='Enchantment — Aura', oracle_text='Enchant creature\nWhenever enchanted creature attacks, put a +1/+1 counter on it. Then if it has three or more +1/+1 counters on it, sacrifice this Aura.\nWhen you sacrifice this Aura, draw two cards.', colors=['U'], color_identity=['U'], keywords=['Enchant']),  # noqa: E501
    card('Stub Giant', set_code='tst', number='20A09', mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Giant', oracle_text='', power='2', toughness='2', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Stub Shock', set_code='tst', number='20A10', mana_cost='{R}', cmc=1.0, type_line='Instant', oracle_text='Stub Shock deals 2 damage to any target.', colors=['R'], color_identity=['R']),  # noqa: E501
    card('Stub Rites', set_code='tst', number='20A11', mana_cost='{1}{U}', cmc=2.0, type_line='Sorcery', oracle_text='Draw a card.', colors=['U'], color_identity=['U']),  # noqa: E501
]
AURAS = ["Spider-Man No More", "Retro-Mutation", "Canopy Cover", "Glamdring", "Hedron Matrix", "Blade of Selves", "Glittering Frost",
         "Ordeal of Thassa"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", AURAS)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def attach(s, name, to):
    aura = put(s, name)
    act(s, "p1", type="attach", card_ids=[aura.id], to=to.id)
    return aura


def test_citizen_with_base_1_1_defender_and_no_other_abilities(cards):
    s = build(cards, "Spider-Man No More", "Retro-Mutation")
    bear = token_of(s, "p1", "Bear", "Token Creature — Bear Warrior", "4/4", "Flying\nTrample")
    attach(s, "Spider-Man No More", bear)
    ch = chars(s, bear)
    assert pt(s, bear) == (1, 1) and ch.subtypes == {"Citizen"}  # 613.4b; creature types replaced (205.3m)
    assert "defender" in ch.keywords and not {"flying", "trample"} & ch.keywords  # 613.1f: its own grant stays
    check(s)


def test_turtle_0_1_loses_all_abilities(cards):
    s = build(cards, "Retro-Mutation")
    bear = token_of(s, "p1", "Bear", "Token Creature — Bear Warrior", "4/4", "Flying")
    attach(s, "Retro-Mutation", bear)
    ch = chars(s, bear)
    assert pt(s, bear) == (0, 1) and ch.subtypes == {"Turtle"} and "flying" not in ch.keywords
    assert "cant_attack" in ch.imposed
    check(s)


def test_cant_be_the_target_of_spells_or_abilities_your_opponents_control_is_hexproof(cards):
    s = build(cards, "Canopy Cover")
    bear = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    attach(s, "Canopy Cover", bear)
    assert "hexproof" in chars(s, bear).keywords
    check(s)


def test_equipped_creature_gets_its_own_mana_value(cards):
    s = build(cards, "Hedron Matrix", "Stub Giant")
    giant = put(s, "Stub Giant")
    token = token_of(s, "p1", "Squirrel", "Token Creature — Squirrel", "1/1")
    eq = put(s, "Hedron Matrix")
    act(s, "p1", type="attach", card_ids=[eq.id], to=giant.id)
    assert pt(s, giant) == (5, 5)  # 202.3: mana value 3
    act(s, "p1", type="attach", card_ids=[eq.id], to=token.id)
    assert pt(s, token) == (1, 1) and pt(s, giant) == (2, 2)  # a token has no mana cost: mana value 0
    check(s)


def test_glamdring_counts_instants_and_sorceries_in_your_graveyard(cards):
    s = build(cards, "Glamdring", "Stub Shock", "Stub Rites", "Stub Giant")
    giant = put(s, "Stub Giant")
    eq = put(s, "Glamdring")
    act(s, "p1", type="attach", card_ids=[eq.id], to=giant.id)
    assert pt(s, giant) == (2, 2) and "first strike" in chars(s, giant).keywords
    for name in ("Stub Shock", "Stub Rites"):
        c = next(c for c in s.state.cards.values() if c.name == name and c.zone == "p1:library")
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})
    assert pt(s, giant) == (4, 2) 
    check(s)


def test_enchanted_land_is_snow(cards):
    s = build(cards, "Glittering Frost")
    land = token_of(s, "p1", "Wood", "Token Land — Forest", "0/0", "{T}: Add {G}.")
    assert "Snow" not in chars(s, land).supertypes
    attach(s, "Glittering Frost", land)
    assert "Snow" in chars(s, land).supertypes  # 205.4a
    check(s)


def test_equipped_creature_has_myriad(cards):
    s = build3(cards, "Blade of Selves")
    bear = token_of(s, "p1", "Bear", "Token Creature — Bear", "3/3")
    eq = put(s, "Blade of Selves")
    act(s, "p1", type="attach", card_ids=[eq.id], to=bear.id)
    next_own_turn(s)
    attack_with(s, bear)  # attacks Bob; Cara is "an opponent other than defending player"
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "choose_one"
          and "token copy" in s.state.rules.decision.prompt)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p3"])
    until(s, lambda s: s.state.turn.phase == "main2")
    assert s.state.players["p2"].life == 37 and s.state.players["p3"].life == 37  # 702.116a, 508.4
    check(s)


@pytest.mark.parametrize("start,sacrificed", [(0, False), (2, True)])
def test_ordeal_counter_then_sacrifice_at_three(cards, start, sacrificed):
    s = build(cards, "Ordeal of Thassa")
    bear = token_of(s, "p1", "Bear", "Token Creature — Bear", "2/2")
    aura = attach(s, "Ordeal of Thassa", bear)
    if start:
        act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=start)
    next_own_turn(s)
    hand = len(s.state.zones.get("p1:hand", []))
    attack_with(s, bear)
    until(s, lambda s: s.state.turn.phase == "main2")
    settle(s)
    assert s.state.cards[bear.id].counters.get("+1/+1", 0) == start + 1
    assert (s.state.cards[aura.id].zone == "p1:graveyard") is sacrificed  # 701.21a; "When you sacrifice this Aura, draw two cards."
    assert len(s.state.zones.get("p1:hand", [])) == hand + (2 if sacrificed else 0)
    check(s)
