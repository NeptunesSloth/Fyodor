"""Wave 50C: Judith, Carnage Connoisseur (CR 2026-09-25), real Oracle text (tests/fixtures/wave50c_cards.json, from data/cards.sqlite). Every scenario checks the
replay and a save and a load.

* 613.1f / 400.7 / ruling 2024-02-02: "Whenever you cast an instant or sorcery spell, choose one — • That spell gains deathtouch and lifelink. • Create a 2/2 red Imp …":
  the spell on the stack has the keywords, so the damage it deals as it resolves destroys the creature it damages (702.2b) and gains its controller that much life (702.15b).
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
from tests.test_rules_wave34b_activated import ask, settle
from tests.wave9c_kit import build, card_named, check, life, mana, put, reloaded, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave50c_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w50c", number=f"M{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
WALL = card("Granite Wall", set_code="w50c", number="P06", mana_cost="{2}{R}", cmc=3.0, type_line="Creature — Wall", oracle_text="", power="0", toughness="6",
            colors=["R"], color_identity=["R"])


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, WALL], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def bolt_the_wall(cards, mode):
    s = build(cards, ["Judith, Carnage Connoisseur", "Lightning Bolt"], ["Granite Wall"], forests=30, islands=30)
    put(s, "Judith, Carnage Connoisseur")
    wall = put(s, "Granite Wall", "p2")
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    mine = life(s)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=[wall.id])
    d = ask(s)
    assert d.kind == "choose_cards" and d.options[0].label == "That spell gains deathtouch and lifelink."
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[mode])
    settle(s)
    return s, wall, mine


def test_judith_spell_with_deathtouch_and_lifelink_kills_the_wall_and_gains_life(cards):
    s, wall, mine = bolt_the_wall(cards, "0:0")
    assert zone_of(s, "Granite Wall", "p2") == "p2:graveyard"  # 3 damage to a 0/6, from a source with deathtouch
    assert life(s) == mine + 3  # lifelink
    check(s)
    assert zone_of(reloaded(s), "Granite Wall", "p2") == "p2:graveyard"


def test_judith_other_mode_leaves_the_spell_plain(cards):
    s, wall, mine = bolt_the_wall(cards, "1:0")
    assert zone_of(s, "Granite Wall", "p2") == "p2:battlefield" and life(s) == mine
    assert [c.name for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"] == ["Imp"]
    check(s)


def test_judith_is_full(cards):
    assert coverage.of_card_data(cards.resolve("Judith, Carnage Connoisseur")).level == "FULL"
