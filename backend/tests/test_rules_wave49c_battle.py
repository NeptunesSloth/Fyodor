"""Wave 49C: "Whenever this creature attacks a battle" (CR 2026-09-25), real Oracle text (tests/fixtures/wave49c_battle_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 310.5, 508.1: the attack was declared against a battle (Thrashing Frontliner: +1/+1, War-Trained Slasher: double its power); an attack on a player does not trigger it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_review34_head import EXTRA as REVIEW34
from tests.test_rules_review34_head import SIEGE, bobs_attack, drive, seasoned
from tests.wave9c_kit import build, check, put, reloaded

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave49c_battle_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()} | {c["name"] for c in REVIEW34}
EXTRA = [card(c["name"], set_code="w49c", number=f"T{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *REVIEW34, *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def ch(s, c):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])


def setup(cards, name):
    """Bob's creature and his Siege (Alice protects it) on the table; Bob's turn, ready to declare attackers."""
    s = build(cards, [], [SIEGE, name])
    creature = put(s, name, "p2")
    siege = put(s, SIEGE, "p2")
    act(s, "p2", type="counter", card_ids=[siege.id], kind="defense", delta=4)
    drive(s, lambda d: "p1" if "p1" in [o.id for o in d.options] else None)
    seasoned(s, creature)
    return reloaded(s), creature, siege


def test_the_cards_are_full(cards):
    for name in ("Thrashing Frontliner", "War-Trained Slasher"):
        assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


@pytest.mark.parametrize(("name", "before", "after"), [("Thrashing Frontliner", (2, 2), (3, 3)), ("War-Trained Slasher", (4, 3), (8, 3))])
def test_attacking_a_battle_triggers_it(cards, name, before, after):
    s, creature, siege = setup(cards, name)
    assert ch(s, creature).pt == before
    bobs_attack(s, [(creature, siege.id)])
    drive(s)
    assert ch(s, creature).pt == after
    check(s)


def test_attacking_a_player_does_not(cards):
    s, creature, _ = setup(cards, "Thrashing Frontliner")
    bobs_attack(s, [(creature, "p1")])
    drive(s)
    assert ch(s, creature).pt == (2, 2)
    check(s)
