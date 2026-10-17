"""Wave 50D: an Aura / Equipment trigger about its host being dealt damage, real Oracle text (tests/fixtures/wave50d_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load (tests/wave9c_kit.check).

* 603.2: an ability triggers when its event happens; the damage is dealt before any state-based action is checked (704.3), so the Aura was still attached to the
  creature that is dealt lethal damage and its "whenever enchanted creature is dealt damage" ability triggers (Druid's Call).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_attachments import token
from tests.test_rules_copy import pay
from tests.test_rules_conditionals import through_combat
from tests.test_rules_wave39b_trigger_damage import attack, block, to_main1
from tests.test_rules_wave40b_attached import cast_on, equip, settle
from tests.wave9c_kit import build, card_named, check, life, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave50d_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="t50d", number=f"D{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def squirrels(s):
    return [c for c in s.state.cards.values() if c.name == "Squirrel" and c.zone.endswith(":battlefield")]


def enchant(s, name, creature, **m):
    """The Aura cast on ``creature`` and resolved."""
    aura = to_hand(s, name)
    pay(s, **m)
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[creature.id])
    settle(s)
    assert s.state.cards[aura.id].attached_to == creature.id
    return aura


def dead(s, c):
    return c.id not in s.state.cards or s.state.cards[c.id].zone.endswith(":graveyard")


def test_druids_call_makes_squirrels_when_the_creature_dies_to_that_damage(cards):
    s = build(cards, ["Druid's Call", "Lightning Bolt"])
    bear = token(s, "p1", "Bear", "2/2")
    aura = enchant(s, "Druid's Call", bear, G=2)
    cast_on(s, "Lightning Bolt", bear, R=1)
    assert dead(s, bear)  # 704.5g
    assert s.state.cards[aura.id].zone.endswith(":graveyard")  # 704.5m
    assert len(squirrels(s)) == 3  # 603.2: the Aura was attached as the damage was dealt
    check(s)


def test_druids_call_makes_squirrels_for_survivable_damage(cards):
    s = build(cards, ["Druid's Call", "Lightning Bolt"])
    bear = token(s, "p1", "Bear", "4/4")
    aura = enchant(s, "Druid's Call", bear, G=2)
    cast_on(s, "Lightning Bolt", bear, R=1)
    assert s.state.cards[bear.id].zone.endswith(":battlefield") and s.state.cards[aura.id].attached_to == bear.id
    assert len(squirrels(s)) == 3
    check(s)


def test_the_enchanted_creatures_controller_gets_the_squirrels(cards):
    """"its controller creates": Bob, whose 2/2 Alice's Druid's Call enchants, gets them (as it last existed, 608.2h)."""
    s = build(cards, ["Druid's Call", "Lightning Bolt"])
    bear = token(s, "p2", "Bear", "2/2")
    enchant(s, "Druid's Call", bear, G=2)
    cast_on(s, "Lightning Bolt", bear, R=1)
    assert dead(s, bear)
    assert [c.controller for c in squirrels(s)] == ["p2"] * 3
    check(s)


def test_an_aura_whose_creature_never_had_it_triggers_nothing(cards):
    s = build(cards, ["Druid's Call", "Lightning Bolt"])
    bear, other = token(s, "p1", "Bear", "2/2"), token(s, "p1", "Goat", "2/2")
    enchant(s, "Druid's Call", other, G=2)
    cast_on(s, "Lightning Bolt", bear, R=1)
    assert dead(s, bear) and not squirrels(s)
    check(s)


@pytest.mark.parametrize(("aura", "mana", "who", "after"), [
    ("Binding Agony", {"R": 1, "B": 1, "C": 1}, "p2", 37),  # "this Aura deals that much damage to that creature's controller"
    ("Ragged Veins", {"B": 1, "C": 1}, "p2", 37),  # "its controller loses that much life"
    ("Spiteful Shadows", {"B": 2}, "p2", 37),  # "it deals that much damage to its controller"
])
def test_the_controller_of_the_dead_creature_is_hurt(cards, aura, mana, who, after):
    s = build(cards, [aura, "Lightning Bolt"])
    bear = token(s, "p2", "Bear", "2/2")
    enchant(s, aura, bear, **mana)
    cast_on(s, "Lightning Bolt", bear, R=1)
    assert dead(s, bear) and life(s, who) == after
    check(s)
