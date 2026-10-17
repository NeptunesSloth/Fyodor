"""Wave 50E: prevention wordings (CR 2026-09-25), real Oracle text (tests/fixtures/wave50e_prevent_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 615.1, 506.4: "Prevent all damage that would be dealt to this creature by creatures it's blocking." (Wall of Vapor), "Prevent all combat damage that would be dealt to this creature by creatures
  blocking it." (Armored Transport) - a static shield whose source group is read from the permanent itself; damage from anything else (a spell) is not prevented.
* 615.7, 205.3m: "Prevent the next 1 damage that would be dealt to target Cleric or Wizard creature this turn." (Wandering Mage) - a creature type is capitalised in the text.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, attack, block, next_turn, settle, stops, to_phase
from tests.wave9c_kit import build, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave50e_prevent_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w50e", number=f"P{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = [c["name"] for c in DATA if c["name"] != "Hill Giant"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_the_cards_are_full(cards):
    for name in FULL:
        assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_wall_of_vapor_takes_no_damage_from_the_creature_it_blocks(cards):
    s = build(cards, ["Hill Giant"], ["Wall of Vapor"])
    giant = put(s, "Hill Giant")
    wall = put(s, "Wall of Vapor", "p2")
    next_turn(s)
    stops(s)
    attack(s, giant)
    block(s, (wall, giant))
    to_phase(s, "main2")
    assert s.state.cards[wall.id].zone == "p2:battlefield" and s.state.cards[wall.id].damage == 0
    check(s)


def test_wall_of_vapor_is_hurt_by_a_spell(cards):
    s = build(cards, ["Lightning Bolt"], ["Wall of Vapor"])
    wall = put(s, "Wall of Vapor", "p2")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[wall.id])
    settle(s)
    assert s.state.cards[wall.id].zone == "p2:graveyard"
    check(s)


def test_armored_transport_takes_no_combat_damage_from_its_blocker(cards):
    s = build(cards, ["Armored Transport"], ["Hill Giant"])
    transport = put(s, "Armored Transport")
    giant = put(s, "Hill Giant", "p2")
    next_turn(s)
    stops(s)
    attack(s, transport)
    block(s, (giant, transport))
    to_phase(s, "main2")
    assert s.state.cards[transport.id].zone == "p1:battlefield" and s.state.cards[transport.id].damage == 0
    assert s.state.cards[giant.id].damage == 2  # (it still deals its 2 damage)
    check(s)


def test_armored_transport_is_hurt_by_a_spell(cards):
    s = build(cards, ["Armored Transport", "Lightning Bolt"])
    transport = put(s, "Armored Transport")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[transport.id])
    settle(s)
    assert s.state.cards[transport.id].zone == "p1:graveyard"
    check(s)


def test_wandering_mage_shields_a_cleric_or_wizard_creature_by_one(cards):
    s = build(cards, ["Wandering Mage", "Lightning Bolt"])
    mage = put(s, "Wandering Mage")
    mana(s, U=1)
    activate(s, "p1", mage, "{U}:", targets=[mage.id])
    settle(s)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[mage.id])
    settle(s)
    assert s.state.cards[mage.id].zone == "p1:battlefield" and s.state.cards[mage.id].damage == 2  # 3 damage, 1 prevented
    check(s)


def test_wandering_mage_cannot_shield_another_kind_of_creature(cards):
    s = build(cards, ["Wandering Mage", "Grizzly Bears"])
    mage = put(s, "Wandering Mage")
    bears = put(s, "Grizzly Bears")
    mana(s, U=1)
    with pytest.raises(ActionError):
        activate(s, "p1", mage, "{U}:", targets=[bears.id])
    check(s)
