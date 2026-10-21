from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.config import load_settings
from app.rules import coverage, selectors
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import build, put, resolve, roundtrip, settle
from tests.wave9c_kit import pt


@pytest.fixture()
def cards(tmp_path):
    settings = load_settings({"FYODOR_DATA_DIR": str(tmp_path), "FYODOR_FRONTEND_DIST": str(tmp_path / "nodist")})
    base = {c["name"]: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / "fixtures" / "relative_union_cards.json").read_text())):
        base[c["name"]] = card(c["name"], set_code="rel", number=str(i), **{k: v for k, v in c.items() if k != "name"})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def token(s, name, kind, colors=(), power="1", types="Creature"):
    act(s, "p1", type="create_token", player="p1", token={"name": name, "type_line": f"Token {types} — {kind}",
                                                         "power": power, "toughness": power, "colors": list(colors)})
    return next(c for c in s.state.cards.values() if c.name == name)


def test_zombie_or_token_anthem_applies_once_and_follows_its_controller(cards):
    assert coverage.of_card_data(cards.resolve("On Wings of Gold")).level == "FULL"
    s = build(cards, ["On Wings of Gold", "Walking Corpse", "Grizzly Bears"], bob=((1, "Walking Corpse"), (10, "Island")))
    wings = put(s, "On Wings of Gold", "battlefield")
    corpse = put(s, "Walking Corpse", "battlefield")
    bear = put(s, "Grizzly Bears", "battlefield")
    theirs = put(s, "Walking Corpse", "battlefield", "p2")
    both = token(s, "Token Zombie", "Zombie")
    human = token(s, "Token Human", "Human")
    assert pt(s, "Walking Corpse") == (3, 3)
    assert pt(s, "Grizzly Bears") == (2, 2)
    assert pt(s, "Token Zombie") == (2, 2)  # It matches both clauses, but this is one effect.
    assert pt(s, "Token Human") == (2, 2)
    plan = Plan(s.state, "p1", cards, None)
    for c in (corpse, both, human):
        assert "flying" in plan.ch(s.state.cards[c.id]).keywords
    for c in (bear, theirs):
        assert "flying" not in plan.ch(s.state.cards[c.id]).keywords
    roundtrip(s)
    act(s, "p2", type="set_controller", card_ids=[wings.id], player="p2")
    assert pt(s, "Walking Corpse") == (2, 2) and pt(s, "Walking Corpse", "p2") == (3, 3)
    assert pt(s, "Token Zombie") == (1, 1)
    roundtrip(s)


def test_green_or_white_additional_reduction_applies_once(cards):
    assert coverage.of_card_data(cards.resolve("Glistening Deluge")).level == "FULL"
    s = build(cards, ["Glistening Deluge"])
    token(s, "Green", "Human", ["G"], "4")
    token(s, "White", "Human", ["W"], "4")
    token(s, "Both", "Human", ["G", "W"], "4")
    token(s, "Neither", "Human", ["R"], "4")
    act(s, "p1", type="add_mana", player="p1", mana={"B": 2, "C": 1})
    act(s, "p1", type="cast_spell", card_id=put(s, "Glistening Deluge", "hand").id)
    settle(s)
    for name in ("Green", "White", "Both"):
        assert pt(s, name) == (1, 1)
    assert pt(s, "Neither") == (3, 3)
    roundtrip(s)


def test_unknown_relative_alternatives_stay_unsupported():
    assert selectors.parse("creatures you control that are Zombies and/or have an activated ability") is None


def test_existing_vehicle_or_creature_selector_remains_supported_and_counts_once(cards):
    assert coverage.of_card_data(cards.resolve("Collision Course")).level == "FULL"
    s = build(cards, ["Grizzly Bears"])
    bear = put(s, "Grizzly Bears", "battlefield")
    act(s, "p1", type="create_token", player="p1", token={"name": "Vehicle", "type_line": "Token Artifact — Vehicle"})
    both = token(s, "Creature Vehicle", "Vehicle", types="Artifact Creature")
    query = selectors.parse("permanents you control that are creatures and/or Vehicles")
    assert query is not None
    found = selectors.candidates(Plan(s.state, "p1", cards, None), query, "p1")
    assert len(found) == len(set(found)) == 3 and bear.id in found and both.id in found
    roundtrip(s)


def test_take_to_the_streets_adds_both_bonuses_only_to_citizens(cards):
    assert coverage.of_card_data(cards.resolve("Take to the Streets")).level == "FULL"
    s = build(cards, ["Take to the Streets"])
    citizen = token(s, "Citizen", "Citizen", power="2")
    human = token(s, "Human", "Human", power="2")
    act(s, "p1", type="add_mana", player="p1", mana={"G": 1, "C": 4})
    act(s, "p1", type="cast_spell", card_id=put(s, "Take to the Streets", "hand").id)
    settle(s)
    assert pt(s, "Citizen") == (5, 5) and pt(s, "Human") == (4, 4)
    plan = Plan(s.state, "p1", cards, None)
    assert "vigilance" in plan.ch(s.state.cards[citizen.id]).keywords
    assert "vigilance" not in plan.ch(s.state.cards[human.id]).keywords
    roundtrip(s)


@pytest.mark.parametrize("wins", [True, False])
def test_fistful_of_force_additional_bonus_requires_winning_the_clash(cards, wins):
    assert coverage.of_card_data(cards.resolve("Fistful of Force")).level == "FULL"
    s = build(cards, ["Fistful of Force", "Grizzly Bears", "Sol Ring"])
    bear = put(s, "Grizzly Bears", "battlefield")
    ring = put(s, "Sol Ring", "hand")
    if wins:
        act(s, "p1", type="move", card_ids=[ring.id], to={"player": "p1", "zone": "library"}, index=0)
    act(s, "p1", type="add_mana", player="p1", mana={"G": 1, "C": 1})
    act(s, "p1", type="cast_spell", card_id=put(s, "Fistful of Force", "hand").id, targets=[bear.id])
    resolve(s, "top", "top")
    assert pt(s, "Grizzly Bears") == ((6, 6) if wins else (4, 4))
    assert ("trample" in Plan(s.state, "p1", cards, None).ch(s.state.cards[bear.id]).keywords) == wins
    roundtrip(s)
