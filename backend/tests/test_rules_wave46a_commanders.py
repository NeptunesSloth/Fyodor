"""Wave 46A: commanders whose only blocker was one line (CR 2026-09-25), real Oracle text
(tests/fixtures/wave46a_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 101.2, 701.6 "Spells and abilities can't be countered" (Spider-Punk): neither a spell nor an ability is countered.
* 120.4b, 202.3e "a source you control with an odd mana value ... deals double that damage" (Obosh): a spell on the stack counts its X.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import pass_until_stack_empty
from tests.wave9c_kit import build, check, life, mana, put, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave46a_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w46a", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
PUNK, OBOSH = "Spider-Punk", "Obosh, the Preypiercer"
FULL = [PUNK, OBOSH]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def cast(s, name, pid="p1", **kw):
    act(s, pid, type="cast_spell", card_id=to_hand(s, name, pid).id, **kw)


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


# ---- 101.2, 701.6: Spider-Punk ---------------------------------------------------------------------------------------------------------------------
def counter_a_bolt(s, punk):
    if punk:
        put(s, PUNK)
    mana(s, R=1)
    bolt = to_hand(s, "Lightning Bolt")
    counter = to_hand(s, "Counterspell", "p2")
    mana(s, "p2", U=2)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    act(s, "p2", type="cast_spell", card_id=counter.id, targets=[bolt.id])
    pass_until_stack_empty(s)


def test_spider_punk_keeps_a_spell_from_being_countered(cards):
    s = build(cards, [PUNK, "Lightning Bolt"], ["Counterspell"])
    counter_a_bolt(s, True)
    assert life(s, "p2") == 37 and zone_of(s, "Counterspell", "p2") == "p2:graveyard"
    check(s)


def test_without_spider_punk_the_spell_is_countered(cards):
    s = build(cards, [PUNK, "Lightning Bolt"], ["Counterspell"])
    counter_a_bolt(s, False)
    assert life(s, "p2") == 40 and zone_of(s, "Lightning Bolt") == "p1:graveyard"
    check(s)


def stifle_the_enters_trigger(s):
    mana(s, G=2)
    stifle = to_hand(s, "Stifle", "p2")
    mana(s, "p2", U=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Elvish Visionary").id)
    hand = len(s.state.zones["p1:hand"])
    for _ in range(8):  # until Bob has priority with the enters trigger on top of the stack
        top = s.state.zones.get("stack") and s.state.cards[s.state.zones["stack"][-1]]
        if top and top.ability is not None and s.state.rules.priority == "p2":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=stifle.id, targets=[top.id])
    pass_until_stack_empty(s)
    return len(s.state.zones["p1:hand"]) - hand


def test_spider_punk_keeps_an_ability_from_being_countered(cards):
    s = build(cards, [PUNK, "Elvish Visionary"], ["Stifle"])
    put(s, PUNK)
    assert stifle_the_enters_trigger(s) == 1  # the draw happened: Stifle did nothing
    check(s)


def test_without_spider_punk_stifle_counters_the_ability(cards):
    s = build(cards, [PUNK, "Elvish Visionary"], ["Stifle"])
    assert stifle_the_enters_trigger(s) == 0
    check(s)


# ---- 120.4b, 202.3e: Obosh -------------------------------------------------------------------------------------------------------------------------
def test_obosh_doubles_the_damage_of_sources_with_an_odd_mana_value_only(cards):
    s = build(cards, [OBOSH, "Lightning Bolt", "Stoke the Flames"], [])
    put(s, OBOSH)
    mana(s, R=5)
    cast(s, "Lightning Bolt", targets=["p2"])  # mana value 1: 3 doubled
    pass_until_stack_empty(s)
    assert life(s, "p2") == 40 - 6
    cast(s, "Stoke the Flames", targets=["p2"])  # mana value 4: 4 as printed
    pass_until_stack_empty(s)
    assert life(s, "p2") == 40 - 6 - 4
    check(s)


def test_obosh_counts_the_x_of_a_spell_on_the_stack(cards):
    s = build(cards, [OBOSH, "Blaze"], [])
    put(s, OBOSH)
    mana(s, R=8)
    cast(s, "Blaze", x_value=2, targets=["p2"])  # {X}{R} with X=2: mana value 3, odd: 2 doubled
    pass_until_stack_empty(s)
    assert life(s, "p2") == 40 - 4
    t = build(cards, [OBOSH, "Blaze"], [])
    put(t, OBOSH)
    mana(t, R=8)
    cast(t, "Blaze", x_value=3, targets=["p2"])  # X=3: mana value 4, even: 3 as printed
    pass_until_stack_empty(t)
    assert life(t, "p2") == 40 - 3
    check(s)
    check(t)


def test_obosh_does_not_double_an_opponents_sources(cards):
    s = build(cards, [OBOSH, "Elvish Visionary"], ["Lightning Bolt"])
    put(s, OBOSH)
    mana(s, G=2)
    mana(s, "p2", R=1)
    bolt = to_hand(s, "Lightning Bolt", "p2")  # (in hand first, so Bob gets priority)
    cast(s, "Elvish Visionary")
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=["p1"])  # in response: a source Alice doesn't control
    pass_until_stack_empty(s)
    assert life(s, "p1") == 37
    check(s)
