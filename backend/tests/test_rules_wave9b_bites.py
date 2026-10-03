"""Wave 9B: "[Several creatures] each deal damage equal to their power to …" (Band Together, Tandem Takedown, Coordinated Clobbering,
Friendly Rivalry, Graceful Takedown, Terrific Team-Up), researched against CR 2026-09-25.

* 120.3: each creature is the source of its own damage (its lifelink and deathtouch count); 608.2h: its power as it is when the
  damage is dealt (after an earlier "+1/+0" of the same spell); all of it dealt at once.
* 608.2b: a creature that is no longer a legal target deals no damage.

Every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana, pass_until_stack_empty
from tests.test_rules_wave9b_exile_permission import build, find, put, roundtrip

EXTRA = [
    card('Band Together', set_code='tst', number='B1', mana_cost='{2}{G}', cmc=3.0, type_line='Instant', oracle_text='Up to two target creatures you control each deal damage equal to their power to another target creature.', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Coordinated Clobbering', set_code='tst', number='B2', mana_cost='{G}', cmc=1.0, type_line='Sorcery', oracle_text='Tap one or two target untapped creatures you control. They each deal damage equal to their power to target creature an opponent controls.', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Tandem Takedown', set_code='tst', number='B3', mana_cost='{1}{G}{G}', cmc=3.0, type_line='Instant', oracle_text='Up to two target creatures you control each get +1/+0 until end of turn. They each deal damage equal to their power to another target creature, planeswalker, or battle.', colors=['G'], color_identity=['G']),  # noqa: E501
    card('Friendly Rivalry', set_code='tst', number='B4', mana_cost='{R}{G}', cmc=2.0, type_line='Instant', oracle_text="Target creature you control and up to one other target legendary creature you control each deal damage equal to their power to target creature you don't control.", colors=['G', 'R'], color_identity=['G', 'R']),  # noqa: E501
    card('Graceful Takedown', set_code='tst', number='B5', mana_cost='{1}{G}', cmc=2.0, type_line='Sorcery', oracle_text="Any number of target enchanted creatures you control and up to one other target creature you control each deal damage equal to their power to target creature you don't control.", colors=['G'], color_identity=['G']),  # noqa: E501
    card('Terrific Team-Up', set_code='tst', number='B6', mana_cost='{3}{G}', cmc=4.0, type_line='Instant', oracle_text='This spell costs {2} less to cast if you control a permanent with mana value 4 or greater.\nOne or two target creatures you control each get +1/+0 until end of turn. They each deal damage equal to their power to target creature an opponent controls.', colors=['G'], color_identity=['G']),  # noqa: E501
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


def tok(s, pid, name, pt, text="", type_line="Token Creature — Test"):
    p, t = pt.split("/")
    act(s, pid, type="create_token", player=pid, token={"name": name, "type_line": type_line, "power": p, "toughness": t, "text": text})
    return next(c for c in s.state.cards.values() if c.name == name and c.owner == pid)


def cast(s, name, targets, counts, **m):
    c = find(s, name)
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "hand"})
    mana(s, **m)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=targets, target_counts=counts)
    pass_until_stack_empty(s)


def damage(s, c):
    return s.state.cards[c.id].damage


def test_band_together_each_creature_deals_its_own_power(cards):
    s = build(cards, p1=("Band Together",))
    a, b = tok(s, "p1", "Ape", "3/3", "Lifelink"), tok(s, "p1", "Bat", "2/2")
    big = tok(s, "p2", "Ogre", "9/9")
    cast(s, "Band Together", [a.id, b.id, big.id], [2, 1], G=3)
    assert damage(s, big) == 5 and s.state.players["p1"].life == 40 + 3  # only the lifelinker's own 3 (120.3f)
    roundtrip(s)


def test_up_to_two_may_be_one_or_none(cards):
    s = build(cards, p1=("Band Together",))
    a = tok(s, "p1", "Ape", "3/3")
    big = tok(s, "p2", "Ogre", "9/9")
    cast(s, "Band Together", [a.id, big.id], [1, 1], G=3)
    assert damage(s, big) == 3
    cast_again = find(s, "Band Together")
    assert cast_again.zone == "p1:graveyard"
    roundtrip(s)


def test_tandem_takedown_pumps_first_then_the_damage_reads_the_new_power(cards):
    s = build(cards, p1=("Tandem Takedown",))
    a, b = tok(s, "p1", "Ape", "3/3"), tok(s, "p1", "Bat", "2/2")
    big = tok(s, "p2", "Ogre", "9/9")
    cast(s, "Tandem Takedown", [a.id, b.id, big.id], [2, 1], G=3)
    assert damage(s, big) == (3 + 1) + (2 + 1)  # 608.2h: their power as the damage is dealt
    roundtrip(s)


def test_coordinated_clobbering_taps_them_and_they_deal_damage(cards):
    s = build(cards, p1=("Coordinated Clobbering",))
    a, b = tok(s, "p1", "Ape", "3/3"), tok(s, "p1", "Bat", "2/2")
    big = tok(s, "p2", "Ogre", "9/9")
    cast(s, "Coordinated Clobbering", [a.id, b.id, big.id], [2, 1], G=1)
    assert s.state.cards[a.id].tapped and s.state.cards[b.id].tapped and damage(s, big) == 5
    roundtrip(s)


def test_friendly_rivalry_two_groups_are_both_sources(cards):
    s = build(cards, p1=("Friendly Rivalry",))
    a = tok(s, "p1", "Ape", "3/3")
    legend = tok(s, "p1", "Lord", "4/4", type_line="Token Legendary Creature — Test")
    big = tok(s, "p2", "Ogre", "9/9")
    cast(s, "Friendly Rivalry", [a.id, legend.id, big.id], [1, 1, 1], R=1, G=1)
    assert damage(s, big) == 7
    roundtrip(s)


def test_a_source_that_left_deals_nothing_but_the_other_does(cards):
    """608.2b: one of the sources is gone when the spell resolves; the other still deals its damage."""
    s = build(cards, p1=("Band Together",))
    a, b = tok(s, "p1", "Ape", "3/3"), tok(s, "p1", "Bat", "2/2")
    big = tok(s, "p2", "Ogre", "9/9")
    band = find(s, "Band Together")
    act(s, "p1", type="move", card_ids=[band.id], to={"player": "p1", "zone": "hand"})
    mana(s, G=3)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="cast_spell", card_id=band.id, targets=[a.id, b.id, big.id], target_counts=[2, 1])
    act(s, "p1", type="move", card_ids=[b.id], to={"player": "p1", "zone": "graveyard"})  # (a token ceases to exist)
    act(s, "p1", type="pass_priority")
    pass_until_stack_empty(s)
    assert damage(s, big) == 3
    roundtrip(s)
