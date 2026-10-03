"""Wave 9C: "Until end of turn, [subject] gains [keywords] and gets +a/+b for each [count]" and its mirror "gets +a/+b for
each [count] and gains [keywords]" (Chorus of Might, Get a Leg Up, Tromp the Domains, Fists of Flame, Sunbathing
Rootwalla, Gold Rush …), researched against CR 2026-09-25.

* 611.2a: one duration ("until end of turn") says how long every part of the sentence lasts, wherever it is written.
* 608.2h: the count a "for each" reads is worked out once, as the spell or ability resolves, and stays (the pump does not
  follow the creature count afterwards).
* 205.3i / 205.3 domain: basic land types among the lands you control, counted once each.

Every scenario uses real Oracle text and checks the replay and a save and a load.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.wave9c_kit import build, card_named, cast, check, mana, pt, put, to_hand

EXTRA = [
    card('Chorus of Might', set_code='wu', number='E01', mana_cost='{3}{G}', cmc=4.0, type_line='Instant', oracle_text='Until end of turn, target creature gets +1/+1 for each creature you control and gains trample.', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Tromp the Domains', set_code='wu', number='E02', mana_cost='{5}{G}', cmc=6.0, type_line='Sorcery', oracle_text='Domain — Until end of turn, creatures you control gain trample and get +1/+1 for each basic land type among lands you control.', colors=['G'], color_identity=['G'], keywords=['Domain']),  # noqa: E501
    card('Sunbathing Rootwalla', set_code='wu', number='E03', mana_cost='{1}{G}', cmc=2.0, type_line='Creature — Lizard', oracle_text='Domain — {3}{G}: Until end of turn, this creature gets +1/+1 for each basic land type among lands you control. Activate only once each turn.', colors=['G'], color_identity=['G'], keywords=['Domain'], power='2', toughness='2'),  # noqa: E501
    card('Gold Rush', set_code='wu', number='E04', mana_cost='{1}{G}', cmc=2.0, type_line='Instant', oracle_text='Create a Treasure token. Until end of turn, up to one target creature gets +2/+2 for each Treasure you control.', colors=['G'], color_identity=['G'], keywords=['Treasure']),  # noqa: E501
    card('Fists of Flame', set_code='wu', number='E05', mana_cost='{1}{R}', cmc=2.0, type_line='Instant', oracle_text="Draw a card. Until end of turn, target creature gains trample and gets +1/+0 for each card you've drawn this turn. (A creature with trample can deal excess combat damage to the player or planeswalker it's attacking.)", colors=['R'], color_identity=['R'], keywords=[]),  # noqa: E501
    card('Haldir, Lórien Lieutenant', set_code='wu', number='E06', mana_cost='{X}{G}', cmc=1.0, type_line='Legendary Creature — Elf Soldier', oracle_text='Haldir enters with X +1/+1 counters on it.\nVigilance\n{5}{G}: Until end of turn, other Elves you control gain vigilance and get +1/+1 for each +1/+1 counter on Haldir.', colors=['G'], color_identity=['G'], keywords=['Vigilance'], power='0', toughness='0'),  # noqa: E501
    card('Green Bear', set_code='wu', number='E10', mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Bear', oracle_text='', power='3', toughness='3', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Second Bear', set_code='wu', number='E11', mana_cost='{2}{G}', cmc=3.0, type_line='Creature — Bear', oracle_text='', power='2', toughness='2', colors=['G'], color_identity=['G'], keywords=[]),  # noqa: E501
    card('Their Ogre', set_code='wu', number='E12', mana_cost='{2}{U}', cmc=3.0, type_line='Creature — Ogre', oracle_text='', power='3', toughness='3', colors=['U'], color_identity=['U'], keywords=[]),  # noqa: E501
]
FULL = ["Chorus of Might", "Tromp the Domains", "Sunbathing Rootwalla", "Gold Rush", "Fists of Flame"]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def has_trample(s, name, pid="p1"):
    from app.rules.plan import Plan

    return "trample" in {k.lower() for k in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name, pid).id]).keywords}


def test_definitions_of_the_full_cards():
    from tests.test_rules_scripts import ch as characteristics

    for c in EXTRA:
        if c["name"] in FULL:
            chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
            assert coverage.of_characteristics(chs).level == "FULL", c["name"]


@pytest.mark.parametrize("text", [
    "Until end of turn, target creature gets +1/+1 for each creature you control and gains trample until end of turn.",
    "Until end of turn, target creature gets +1/+1 for each creature you control and gains a counter.",
    "Until end of turn, target creature gets +1/+1 until end of turn for each creature you control and gains trample.",
    "Target creature gets +1/+1 for each creature you control and gains trample."])
def test_other_durations_and_keywords_stay_manual(text):
    from tests.test_rules_scripts import ch as characteristics

    assert coverage.of_characteristics(characteristics("Test", "Instant", text)).level != "FULL", text


def test_chorus_of_might_counts_your_creatures_once_as_it_resolves(cards):
    s = build(cards, ("Chorus of Might", "Green Bear", "Second Bear"), ("Their Ogre",))
    put(s, "Green Bear")
    put(s, "Second Bear")
    put(s, "Their Ogre", "p2")
    to_hand(s, "Chorus of Might")
    mana(s, G=4)
    cast(s, "Chorus of Might", targets=[card_named(s, "Green Bear").id])
    assert pt(s, "Green Bear") == (5, 5) and has_trample(s, "Green Bear")  # (two creatures: +2/+2)
    assert pt(s, "Second Bear") == (2, 2) and not has_trample(s, "Second Bear")
    assert pt(s, "Their Ogre", "p2") == (3, 3)
    act(s, "p1", type="move", card_ids=[card_named(s, "Second Bear").id], to={"zone": "graveyard"})
    assert pt(s, "Green Bear") == (5, 5)  # (counted when it resolved)
    check(s)


def test_tromp_the_domains_counts_basic_land_types_among_your_lands(cards):
    s = build(cards, ("Tromp the Domains", "Green Bear", "Second Bear", "Mountain", "Swamp"), ("Their Ogre",))
    put(s, "Green Bear")
    put(s, "Second Bear")
    put(s, "Their Ogre", "p2")
    for n in ("Mountain", "Swamp"):
        put(s, n)
    forest = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library"][0]
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    to_hand(s, "Tromp the Domains")
    mana(s, G=6)
    cast(s, "Tromp the Domains")
    # Forest, Mountain, Swamp: three basic land types
    assert pt(s, "Green Bear") == (6, 6) and pt(s, "Second Bear") == (5, 5)
    assert has_trample(s, "Green Bear") and has_trample(s, "Second Bear")
    assert pt(s, "Their Ogre", "p2") == (3, 3) and not has_trample(s, "Their Ogre", "p2")
    check(s)


def test_sunbathing_rootwalla_pumps_itself_by_the_basic_land_types(cards):
    s = build(cards, ("Sunbathing Rootwalla", "Island"), ())
    root = put(s, "Sunbathing Rootwalla")
    forest = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library"][0]
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "battlefield"})
    put(s, "Island")
    mana(s, G=4)
    act(s, "p1", type="activate_ability", card_id=root.id, ability=0)
    settle(s)
    assert pt(s, "Sunbathing Rootwalla") == (4, 4)  # Forest and Island
    check(s)


def test_gold_rush_counts_the_treasure_it_makes(cards):
    s = build(cards, ("Gold Rush", "Green Bear"), ())
    put(s, "Green Bear")
    to_hand(s, "Gold Rush")
    mana(s, G=2)
    cast(s, "Gold Rush", targets=[card_named(s, "Green Bear").id], target_counts=[1])
    assert pt(s, "Green Bear") == (5, 5)  # one Treasure: +2/+2
    check(s)
