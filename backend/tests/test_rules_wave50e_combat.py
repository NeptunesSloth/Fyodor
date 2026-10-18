"""Wave 50E: "it" in a self trigger's damage prevention or redirection (CR 2026-09-25), real Oracle text (tests/fixtures/wave50e_combat_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 615.1, 509.1h: "Whenever this creature becomes blocked, prevent all combat damage that would be dealt by it this turn." (Ignoble Soldier) - it deals none to its blocker, and nothing changes when unblocked.
* 614.9, 702.37e: "When this creature is turned face up, all damage that would be dealt to it this turn is dealt to target creature instead." (Karona's Zealot).
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
from tests.test_rules_wave12a_counters_keywords import answer
from tests.test_rules_wave34b_activated import attack, block, next_turn, settle, stops, to_phase
from tests.wave9c_kit import build, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave50e_combat_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w50e", number=f"C{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_the_cards_are_full(cards):
    for c in DATA:
        assert coverage.of_card_data(cards.resolve(c["name"])).level == "FULL", c["name"]


def test_ignoble_soldier_deals_no_combat_damage_once_blocked(cards):
    s = build(cards, ["Ignoble Soldier"], ["Grizzly Bears"])
    soldier = put(s, "Ignoble Soldier")
    bears = put(s, "Grizzly Bears", "p2")
    next_turn(s)
    stops(s)
    attack(s, soldier)
    block(s, (bears, soldier))
    answer(s)
    to_phase(s, "main2")
    assert s.state.cards[bears.id].zone == "p2:battlefield" and s.state.cards[bears.id].damage == 0
    assert s.state.cards[soldier.id].zone == "p1:graveyard"  # (the Bears' 2 damage kills the 3/1)
    check(s)


def test_ignoble_soldier_unblocked_hits_the_player(cards):
    s = build(cards, ["Ignoble Soldier"])
    soldier = put(s, "Ignoble Soldier")
    next_turn(s)
    attack(s, soldier)
    to_phase(s, "main2")
    assert s.state.players["p2"].life == 37
    check(s)


def test_karonas_zealot_sends_the_damage_to_another_creature_when_turned_face_up(cards):
    s = build(cards, ["Karona's Zealot", "Lightning Bolt"], ["Grizzly Bears"])
    zealot = next(c for c in s.state.cards.values() if c.name == "Karona's Zealot")
    act(s, "p1", type="move", card_ids=[zealot.id], to={"player": "p1", "zone": "battlefield"}, face_down=True, face_down_kind="morph")
    bears = put(s, "Grizzly Bears", "p2")
    mana(s, W=2, C=3)
    act(s, "p1", type="turn_face_up", card_id=zealot.id)  # 702.37e: Morph {3}{W}{W}
    answer(s, bears.id)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[zealot.id])
    settle(s)
    assert s.state.cards[zealot.id].damage == 0 and s.state.cards[bears.id].zone == "p2:graveyard"
    check(s)


def test_karonas_zealot_face_down_takes_its_damage(cards):
    s = build(cards, ["Karona's Zealot", "Lightning Bolt"])
    zealot = next(c for c in s.state.cards.values() if c.name == "Karona's Zealot")
    act(s, "p1", type="move", card_ids=[zealot.id], to={"player": "p1", "zone": "battlefield"}, face_down=True, face_down_kind="morph")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[zealot.id])
    settle(s)
    assert s.state.cards[zealot.id].zone == "p1:graveyard"  # (a face-down 2/2 has no such ability)
    check(s)
