"""Wave 9C: "gets an additional +N/+N as long as …" statics (Strange Augmentation, Patriarch's Desire, Divine Sacrament,
Zealot's Conviction, Taste for Mayhem), researched against CR 2026-09-25.

"Additional" only says the modification comes on top of the line before it: both are layer 7c bonuses and add (613.4c).
The condition is read continuously (611.3a). Every scenario checks the replay and a save and a load.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named, cast, check, mana, pt, put, to_hand

EXTRA = [
    card("Patriarch's Desire", set_code='ws', number='E01', mana_cost='{3}{B}', cmc=4.0, type_line='Enchantment — Aura', oracle_text='Enchant creature\nEnchanted creature gets +2/-2.\nThreshold — Enchanted creature gets an additional +2/-2 as long as there are seven or more cards in your graveyard.', colors=['B'], color_identity=['B'], keywords=['Enchant', 'Threshold']),  # noqa: E501
    card('Strange Augmentation', set_code='ws', number='E02', mana_cost='{B}', cmc=1.0, type_line='Enchantment — Aura', oracle_text='Enchant creature\nEnchanted creature gets +1/+1.\nDelirium — Enchanted creature gets an additional +2/+2 as long as there are four or more card types among cards in your graveyard.', colors=['B'], color_identity=['B'], keywords=['Delirium', 'Enchant']),  # noqa: E501
    card('Divine Sacrament', set_code='ws', number='E03', mana_cost='{1}{W}{W}', cmc=3.0, type_line='Enchantment', oracle_text='White creatures get +1/+1.\nThreshold — White creatures get an additional +1/+1 as long as there are seven or more cards in your graveyard.', colors=['W'], color_identity=['W'], keywords=['Threshold']),  # noqa: E501
    card("Zealot's Conviction", set_code='ws', number='E04', mana_cost='{W}', cmc=1.0, type_line='Enchantment — Aura', oracle_text='Flash\nEnchant creature\nEnchanted creature gets +1/+1.\nCorrupted — As long as an opponent has three or more poison counters, enchanted creature gets an additional +1/+0 and has first strike.', colors=['W'], color_identity=['W'], keywords=['Enchant', 'Corrupted', 'Flash']),  # noqa: E501
    card('Taste for Mayhem', set_code='ws', number='E05', mana_cost='{R}', cmc=1.0, type_line='Enchantment — Aura', oracle_text='Enchant creature\nEnchanted creature gets +2/+0.\nHellbent — Enchanted creature gets an additional +2/+0 as long as you have no cards in hand.', colors=['R'], color_identity=['R'], keywords=['Enchant', 'Hellbent']),  # noqa: E501
    card('Green Bear', set_code='ws', number='E10', mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Bear', oracle_text='', power='3', toughness='3', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('White Knight', set_code='ws', number='E11', mana_cost='{1}{W}', cmc=2.0, type_line='Creature — Knight', oracle_text='', power='2', toughness='2', colors=['W'], color_identity=['W'], keywords=[]),  # noqa: E501
    card('Steel Golem', set_code='ws', number='E13', mana_cost='{3}', cmc=3.0, type_line='Artifact Creature — Golem', oracle_text='', power='3', toughness='3', colors=[], color_identity=[], keywords=[]),  # noqa: E501
    card('White Omen', set_code='ws', number='E15', mana_cost='{1}{W}', cmc=2.0, type_line='Enchantment', oracle_text='', colors=['W'], color_identity=['W'], keywords=[]),  # noqa: E501
]

@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def aura_on(s, aura, host, pid="p1", **m):
    to_hand(s, aura)
    mana(s, **m)
    cast(s, aura, targets=[card_named(s, host, pid).id])


def bin_cards(s, *names):
    for n in names:
        c = card_named(s, n)
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})


def forests_to_graveyard(s, n):
    for c in [c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library"][:n]:
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})


def test_definitions_of_the_full_cards():
    from tests.test_rules_scripts import ch as characteristics

    for c in EXTRA:
        if c["name"] in ("Patriarch's Desire", "Strange Augmentation", "Divine Sacrament", "Zealot's Conviction",
                         "Taste for Mayhem"):
            chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
            assert coverage.of_characteristics(chs).level == "FULL", c["name"]


def test_other_wordings_with_additional_stay_manual():
    from tests.test_rules_scripts import ch as characteristics

    for text in ("Enchant creature\nEnchanted creature gets an additional +2/+2 and flying as long as you have no cards in hand.",
                 "Enchant creature\nEnchanted creature gets an additional card as long as you have no cards in hand."):
        assert coverage.of_characteristics(characteristics("Test", "Enchantment — Aura", text)).level != "FULL", text


def test_strange_augmentation_adds_two_with_four_card_types_in_the_graveyard(cards):
    s = build(cards, ("Green Bear", "Strange Augmentation", "Steel Golem", "White Omen"))
    put(s, "Green Bear")
    aura_on(s, "Strange Augmentation", "Green Bear", B=1)
    assert pt(s, "Green Bear") == (4, 4)
    forests_to_graveyard(s, 1)
    bin_cards(s, "Steel Golem")  # artifact + creature + land: three types
    assert pt(s, "Green Bear") == (4, 4)
    bin_cards(s, "White Omen")  # + enchantment: four types
    assert pt(s, "Green Bear") == (6, 6)
    check(s)


def test_patriarchs_desire_adds_two_and_minus_two_again_with_threshold(cards):
    s = build(cards, ("Green Bear", "Patriarch's Desire"))
    put(s, "Green Bear")
    aura_on(s, "Patriarch's Desire", "Green Bear", B=1, G=3)
    assert pt(s, "Green Bear") == (5, 1)
    forests_to_graveyard(s, 6)
    assert pt(s, "Green Bear") == (5, 1)  # six cards
    forests_to_graveyard(s, 1)
    assert pt(s, "Green Bear") == (7, -1)  # seven: the second +2/-2 (the creature would then die: 704.5f)
    check(s)


def test_divine_sacrament_only_pumps_white_creatures_and_only_with_threshold(cards):
    s = build(cards, ("White Knight", "Green Bear", "Divine Sacrament"))
    put(s, "White Knight")
    put(s, "Green Bear")
    to_hand(s, "Divine Sacrament")
    mana(s, W=2, G=1)
    cast(s, "Divine Sacrament")
    assert pt(s, "White Knight") == (3, 3) and pt(s, "Green Bear") == (3, 3)
    forests_to_graveyard(s, 7)
    assert pt(s, "White Knight") == (4, 4) and pt(s, "Green Bear") == (3, 3)
    check(s)


def test_taste_for_mayhem_needs_an_empty_hand(cards):
    s = build(cards, ("Green Bear", "Taste for Mayhem", "White Knight"))
    put(s, "Green Bear")
    to_hand(s, "White Knight")
    aura_on(s, "Taste for Mayhem", "Green Bear", R=1)
    hand = [c.id for c in s.state.cards.values() if c.zone == "p1:hand"]
    assert hand  # the Knight is still in hand: only the first +2/+0
    assert pt(s, "Green Bear") == (5, 3)
    act(s, "p1", type="move", card_ids=hand, to={"zone": "graveyard"})
    assert pt(s, "Green Bear") == (7, 3)
    check(s)


def test_zealots_conviction_needs_an_opponent_with_three_poison_counters(cards):
    s = build(cards, ("Green Bear", "Zealot's Conviction"))
    put(s, "Green Bear")
    aura_on(s, "Zealot's Conviction", "Green Bear", W=1)
    assert pt(s, "Green Bear") == (4, 4)
    act(s, "p1", type="resource", player="p2", key="poison", delta=2)
    assert pt(s, "Green Bear") == (4, 4)
    act(s, "p1", type="resource", player="p2", key="poison", delta=1)
    assert pt(s, "Green Bear") == (5, 4)
    check(s)
