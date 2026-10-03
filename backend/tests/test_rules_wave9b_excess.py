"""Wave 9B: "excess damage dealt this way" (Goblin Negotiation, Hell to Pay, Windswift Slice, Lacerate Flesh, Razor Rings, Orbital
Plunge, Overwhelming Victory), researched against CR 2026-09-25.

* 120.10: if the sources together dealt more damage to a creature than lethal damage (its toughness less the damage already
  marked), excess damage equal to the difference was dealt; a planeswalker's is what exceeds its loyalty before the damage.
* It is the damage actually dealt (after prevention and replacement), read before the damage is marked (608.2h).

Every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.rules import coverage, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana, pass_until_stack_empty
from tests.test_rules_wave9b_exile_permission import build, find, put, roundtrip

EXTRA = [
    card('Goblin Negotiation', set_code='tst', number='X01', mana_cost='{X}{R}{R}', cmc=2.0, type_line='Sorcery', oracle_text='Goblin Negotiation deals X damage to target creature. Create a number of 1/1 red Goblin creature tokens equal to the amount of excess damage dealt to that creature this way.', colors=['R'], color_identity=['R']),  # noqa: E501
    card('Hell to Pay', set_code='tst', number='X02', mana_cost='{X}{R}', cmc=1.0, type_line='Sorcery', oracle_text='Hell to Pay deals X damage to target creature. Create a number of tapped Treasure tokens equal to the amount of excess damage dealt to that creature this way.', colors=['R'], color_identity=['R'], keywords=['Treasure']),  # noqa: E501
    card('Windswift Slice', set_code='tst', number='X03', mana_cost='{2}{G}', cmc=3.0, type_line='Instant', oracle_text="Target creature you control deals damage equal to its power to target creature you don't control. Create a number of 1/1 green Elf Warrior creature tokens equal to the amount of excess damage dealt this way.", colors=['G'], color_identity=['G']),  # noqa: E501
    card('Lacerate Flesh', set_code='tst', number='X04', mana_cost='{4}{R}', cmc=5.0, type_line='Sorcery', oracle_text='Lacerate Flesh deals 4 damage to target creature. Create a number of Blood tokens equal to the amount of excess damage dealt to that creature this way. (They\'re artifacts with "{1}, {T}, Discard a card, Sacrifice this token: Draw a card.")', colors=['R'], color_identity=['R']),  # noqa: E501
    card('Razor Rings', set_code='tst', number='X05', mana_cost='{1}{W}', cmc=2.0, type_line='Instant', oracle_text='Razor Rings deals 4 damage to target attacking or blocking creature. You gain life equal to the excess damage dealt this way.', colors=['W'], color_identity=['W']),  # noqa: E501
    card('Orbital Plunge', set_code='tst', number='X06', mana_cost='{3}{R}', cmc=4.0, type_line='Sorcery', oracle_text='Orbital Plunge deals 6 damage to target creature. If excess damage was dealt this way, create a Lander token. (It\'s an artifact with "{2}, {T}, Sacrifice this token: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.")', colors=['R'], color_identity=['R']),  # noqa: E501
    card('Overwhelming Victory', set_code='tst', number='X07', mana_cost='{4}{R}', cmc=5.0, type_line='Instant — Lesson', oracle_text='Overwhelming Victory deals 5 damage to target creature. Each creature you control gains trample and gets +X/+0 until end of turn, where X is the amount of excess damage dealt this way.', colors=['R'], color_identity=['R']),  # noqa: E501
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


def test_the_wording_is_exact():
    ok = scripts.parse_effects("~ deals 6 damage to target creature. If excess damage was dealt this way, create a Lander token.")
    assert ok is not None and ok[0][0] == {"do": "damage", "who": "target", "n": 6, "bind_excess": "excess_dealt"}
    # nothing that reads the excess without one plain single-target damage instruction before it
    for text in ("You gain life equal to the excess damage dealt this way.",
                 "~ deals 4 damage to each creature. You gain life equal to the excess damage dealt this way.",
                 "~ deals 4 damage to target creature and 2 damage to you. You gain life equal to the excess damage dealt this way.",
                 "~ deals 4 damage to target creature. Draw a card. You gain life equal to the excess damage dealt this way."):
        found = scripts.parse_effects(text)
        assert found is None or all("bind_excess" not in e or e["who"] == "target" for e in found[0]), text
    assert scripts.parse_effects("You gain life equal to the excess damage dealt this way.") is None


def cast(s, name, targets, x=None, counts=None, **m):
    c = find(s, name)
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "hand"})
    mana(s, **m)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=targets, **({"x_value": x} if x is not None else {}),
        **({"target_counts": counts} if counts else {}))
    pass_until_stack_empty(s)


def count(s, name, pid="p1"):
    return sum(1 for c in s.state.cards.values() if c.name == name and c.controller == pid and c.zone.endswith(":battlefield"))


def test_goblin_negotiation_makes_a_goblin_for_each_point_of_excess(cards):
    s = build(cards, p1=("Goblin Negotiation",), p2=("Grizzly Bears",))
    bears = put(s, "Grizzly Bears", "battlefield", pid="p2")
    cast(s, "Goblin Negotiation", [bears.id], x=5, R=7)
    assert s.state.cards[bears.id].zone == "p2:graveyard"
    assert count(s, "Goblin") == 3  # 5 damage to a 2/2: 3 more than lethal (120.10)
    roundtrip(s)


def test_exactly_lethal_is_no_excess(cards):
    s = build(cards, p1=("Goblin Negotiation",), p2=("Grizzly Bears",))
    bears = put(s, "Grizzly Bears", "battlefield", pid="p2")
    cast(s, "Goblin Negotiation", [bears.id], x=2, R=4)
    assert s.state.cards[bears.id].zone == "p2:graveyard" and count(s, "Goblin") == 0
    roundtrip(s)


def test_damage_already_marked_makes_less_lethal(cards):
    s = build(cards, p1=("Goblin Negotiation",), p2=("Grizzly Bears",))
    bears = put(s, "Grizzly Bears", "battlefield", pid="p2")
    act(s, "p1", type="set_damage", card_ids=[bears.id], value=1)
    cast(s, "Goblin Negotiation", [bears.id], x=2, R=4)
    assert count(s, "Goblin") == 1  # one more damage was lethal; 2 dealt: 1 in excess
    roundtrip(s)


def test_hell_to_pay_makes_tapped_treasure(cards):
    s = build(cards, p1=("Hell to Pay",), p2=("Grizzly Bears",))
    bears = put(s, "Grizzly Bears", "battlefield", pid="p2")
    cast(s, "Hell to Pay", [bears.id], x=4, R=5)
    treasures = [c for c in s.state.cards.values() if c.name == "Treasure" and c.zone == "p1:battlefield"]
    assert len(treasures) == 2 and all(t.tapped for t in treasures)
    roundtrip(s)


def test_windswift_slice_bite_counts_the_excess_of_the_bite(cards):
    s = build(cards, p1=("Windswift Slice",), p2=("Grizzly Bears",))
    act(s, "p1", type="create_token", player="p1", token={"name": "Brute", "type_line": "Token Creature — Test", "power": "4",
                                                         "toughness": "4", "text": ""})
    brute = find(s, "Brute")
    bears = put(s, "Grizzly Bears", "battlefield", pid="p2")
    cast(s, "Windswift Slice", [brute.id, bears.id], counts=[1, 1], R=0, G=3)
    assert s.state.cards[bears.id].zone == "p2:graveyard"
    assert count(s, "Elf Warrior") == 2  # power 4 against toughness 2
    roundtrip(s)


def test_orbital_plunge_conditional_on_excess(cards):
    s = build(cards, p1=("Orbital Plunge",), p2=("Grizzly Bears",))
    bears = put(s, "Grizzly Bears", "battlefield", pid="p2")
    cast(s, "Orbital Plunge", [bears.id], R=4)
    assert count(s, "Lander") == 1
    roundtrip(s)


def test_lacerate_flesh_and_overwhelming_victory(cards):
    s = build(cards, p1=("Lacerate Flesh", "Overwhelming Victory"), p2=("Grizzly Bears", "Ambush Viper"))
    bears = put(s, "Grizzly Bears", "battlefield", pid="p2")
    cast(s, "Lacerate Flesh", [bears.id], R=5)
    assert count(s, "Blood") == 2
    viper = put(s, "Ambush Viper", "battlefield", pid="p2")
    act(s, "p1", type="create_token", player="p1", token={"name": "Brute", "type_line": "Token Creature — Test", "power": "4",
                                                         "toughness": "4", "text": ""})
    brute = find(s, "Brute")
    cast(s, "Overwhelming Victory", [viper.id], R=5)  # Ambush Viper is a 2/1: 5 damage, 4 in excess
    assert s.state.cards[viper.id].zone == "p2:graveyard"
    from tests.test_rules_attachments import ch

    assert ch(s, brute).pt == (8, 4) and "trample" in ch(s, brute).keywords  # +4/+0: the excess of 5 damage on a 2/1
    roundtrip(s)
