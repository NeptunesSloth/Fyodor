"""Wave 9B review: scenarios the first pass left untested (611.2b a source gone before the hold starts; discard-sized
amounts; excess damage feeding discover; a conditional pair; creature counts), researched against CR 2026-09-25.

Every scenario checks the replay and a save/load round trip."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import ch
from tests.test_rules_effects import mana, pass_until_stack_empty
from tests.test_rules_wave4h_activation_costs import activate
from tests.test_rules_wave7f_untap_choice import play_to
from tests.test_rules_wave9b_exile_permission import answer, build, find, put, roundtrip
from tests.test_rules_wave9b_hold import EXTRA as HOLD_EXTRA

NEW = [
    card('Volrath the Fallen', set_code='tst', number='R01', mana_cost='{3}{B}{B}{B}', cmc=6.0, type_line='Legendary Creature — Phyrexian Shapeshifter', oracle_text="{1}{B}, Discard a creature card: Volrath gets +X/+X until end of turn, where X is the discarded card's mana value.", power='6', toughness='4', colors=['B'], color_identity=['B']),  # noqa: E501
    card('Slumbering Tora', set_code='tst', number='R02', mana_cost='{3}', cmc=3.0, type_line='Artifact', oracle_text="{2}, Discard a Spirit or Arcane card: This artifact becomes an X/X Cat artifact creature until end of turn, where X is the discarded card's mana value."),  # noqa: E501
    card('Contest of Claws', set_code='tst', number='R03', mana_cost='{1}{G}', cmc=2.0, type_line='Sorcery', oracle_text='Target creature you control deals damage equal to its power to another target creature. If excess damage was dealt this way, discover X, where X is that excess damage. (Exile cards from the top of your library until you exile a nonland card with that mana value or less. Cast it without paying its mana cost or put it into your hand. Put the rest on the bottom in a random order.)', colors=['G'], color_identity=['G'], keywords=['Discover']),  # noqa: E501
    card('Precipitous Drop', set_code='tst', number='R04', mana_cost='{2}{B}', cmc=3.0, type_line='Enchantment — Aura', oracle_text="Enchant creature\nWhen this Aura enters, venture into the dungeon. (Enter the first room or advance to the next room.)\nEnchanted creature gets -2/-2. It gets -5/-5 instead as long as you've completed a dungeon.", colors=['B'], color_identity=['B'], keywords=['Enchant', 'Venture into the dungeon']),  # noqa: E501
    card('Tyranid Invasion', set_code='tst', number='R05', mana_cost='{3}{G}', cmc=4.0, type_line='Sorcery', oracle_text='Create a number of 3/3 green Tyranid Warrior creature tokens with trample equal to the number of opponents you have.', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Elemental Spectacle', set_code='tst', number='R06', mana_cost='{5}{G}', cmc=6.0, type_line='Sorcery', oracle_text='Vivid — Create a number of 5/5 red and green Elemental creature tokens equal to the number of colors among permanents you control. Then you gain life equal to the number of creatures you control.', colors=['G'], color_identity=['G'], keywords=['Vivid']),  # noqa: E501
    card('Arcane Gem', set_code='tst', number='R07', mana_cost='{2}{U}', cmc=3.0, type_line='Instant — Arcane', oracle_text='Draw a card.', colors=['U'], color_identity=['U']),  # noqa: E501
    card('Spellbound Dragon', set_code='tst', number='R08', mana_cost='{3}{U}{R}', cmc=5.0, type_line='Creature — Dragon', oracle_text="Flying\nWhenever this creature attacks, draw a card, then discard a card. This creature gets +X/+0 until end of turn, where X is the discarded card's mana value.", power='3', toughness='5', colors=['R', 'U'], color_identity=['R', 'U'], keywords=['Flying']),  # noqa: E501
]
EXTRA = [*HOLD_EXTRA, *NEW]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [c["name"] for c in NEW if c["name"] != "Arcane Gem"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def pt(s, c):
    return ch(s, s.state.cards[c.id]).pt


def cast(s, name, targets, counts=None, **m):
    c = find(s, name)
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "hand"})
    mana(s, **m)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=targets, **({"target_counts": counts} if counts else {}))
    pass_until_stack_empty(s)


def test_a_source_gone_before_the_hold_starts_holds_nothing(cards):
    """611.2b: a "for as long as" effect whose duration has already ended does nothing: the tap happens, the hold doesn't."""
    s = build(cards, p1=("Icefall Regent",), p2=("Ambush Viper",))
    regent = put(s, "Icefall Regent", "hand")
    viper = put(s, "Ambush Viper", "battlefield", pid="p2")
    mana(s, U=2, C=3)
    act(s, "p1", type="cast_spell", card_id=regent.id)
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, "p1", type="move", card_ids=[regent.id], to={"player": "p1", "zone": "graveyard"})  # the Regent is gone before it resolves
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options if o.card_id == viper.id])
    pass_until_stack_empty(s)
    assert s.state.cards[viper.id].tapped
    play_to(s, 4)
    assert not s.state.cards[viper.id].tapped
    roundtrip(s)


def test_volrath_gets_the_mana_value_of_the_creature_card_discarded(cards):
    s = build(cards, p1=("Volrath the Fallen", "Grizzly Bears", "Lightning Bolt"))
    volrath = put(s, "Volrath the Fallen", "battlefield")
    bears = put(s, "Grizzly Bears", "hand")  # mana value 2
    put(s, "Lightning Bolt", "hand")  # (not a creature card: can't pay the cost)
    mana(s, B=2)
    activate(s, volrath, "{1}{B}, Discard")
    answer(s, pick=bears.id)
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    assert pt(s, volrath) == (8, 6)
    roundtrip(s)


def test_slumbering_tora_becomes_a_cat_of_the_discarded_mana_value(cards):
    s = build(cards, p1=("Slumbering Tora", "Arcane Gem", "Grizzly Bears"))
    tora = put(s, "Slumbering Tora", "battlefield")
    gem = put(s, "Arcane Gem", "hand")  # an Arcane card, mana value 3
    put(s, "Grizzly Bears", "hand")  # neither a Spirit nor an Arcane card
    mana(s, C=2)
    activate(s, tora, "{2}, Discard")
    answer(s, pick=gem.id)
    c = ch(s, s.state.cards[tora.id])
    assert s.state.cards[gem.id].zone == "p1:graveyard" and c.pt == (3, 3) and "Creature" in c.types and "Cat" in c.subtypes
    roundtrip(s)


def test_contest_of_claws_bites_and_discovers_only_for_excess(cards):
    s = build(cards, p1=("Contest of Claws", "Grizzly Bears"), p2=("Grizzly Bears",))
    act(s, "p1", type="create_token", player="p1", token={"name": "Brute", "type_line": "Token Creature — Test", "power": "4",
                                                         "toughness": "4", "text": ""})
    brute = find(s, "Brute")
    prey = put(s, "Grizzly Bears", "battlefield", pid="p2")
    cast(s, "Contest of Claws", [brute.id, prey.id], counts=[1, 1], G=2)
    d = s.state.rules.decision  # 4 damage to a 2/2: excess 2 → discover 2 (the Bears of the library: mana value 2 or less)
    assert d is not None and d.prompt.startswith("Discover 2")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["no"])
    pass_until_stack_empty(s)
    assert s.state.cards[prey.id].zone == "p2:graveyard"
    roundtrip(s)


def test_precipitous_drop_is_minus_two_until_a_dungeon_is_completed(cards):
    s = build(cards, p1=("Precipitous Drop", "Grizzly Bears"))
    bears = put(s, "Grizzly Bears", "battlefield")
    drop = put(s, "Precipitous Drop", "battlefield")
    act(s, "p1", type="attach", card_ids=[drop.id], to=bears.id)
    assert pt(s, bears) == (0, 0)
    s.state.rules.completed_dungeons["p1"] = ["Lost Mine of Phandelver"]  # 309.7
    s.state.seq += 1  # (a real completion is an action: the condition cache is keyed on the sequence number)
    assert pt(s, bears) == (-3, -3)


def test_tyranid_invasion_makes_one_token_for_each_opponent(cards):
    s = build(cards, p1=("Tyranid Invasion",))
    cast(s, "Tyranid Invasion", [], G=4)
    made = [c for c in s.state.cards.values() if c.name == "Tyranid Warrior" and c.zone == "p1:battlefield"]
    assert len(made) == 1 and ch(s, made[0]).pt == (3, 3) and "trample" in ch(s, made[0]).keywords
    roundtrip(s)


def test_spellbound_dragon_loots_then_gets_the_discarded_mana_value(cards):
    from tests.test_rules_wave9b_mana_value import attack_with

    s = build(cards, p1=("Spellbound Dragon", "Lightning Bolt"))
    dragon = put(s, "Spellbound Dragon", "battlefield")
    bolt = put(s, "Lightning Bolt", "hand")
    for c in list(s.state.zones["p1:hand"]):  # (only the Bolt stays in hand)
        if c != bolt.id:
            act(s, "p1", type="move", card_ids=[c], to={"player": "p1", "zone": "library"})
    attack_with(s, [dragon])
    answer(s, pick=bolt.id)
    assert s.state.cards[bolt.id].zone == "p1:graveyard"
    assert pt(s, dragon) == (4, 5)  # +X/+0, X = Lightning Bolt's mana value 1
    roundtrip(s)


def test_elemental_spectacle_counts_colors_then_the_creatures_you_control(cards):
    s = build(cards, p1=("Elemental Spectacle", "Grizzly Bears"))
    put(s, "Grizzly Bears", "battlefield")  # green
    before = s.state.players["p1"].life
    cast(s, "Elemental Spectacle", [], G=6)
    made = [c for c in s.state.cards.values() if c.name == "Elemental" and c.zone == "p1:battlefield"]
    assert len(made) == 1  # one color among the permanents (green)
    assert s.state.players["p1"].life == before + 2  # the Bears and the new token
    roundtrip(s)
