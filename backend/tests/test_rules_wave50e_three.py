"""Wave 50E: one source dealing three amounts to three different targets (CR 2026-09-25), real Oracle text (tests/fixtures/wave50e_three_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 115.1, 601.2c, 608.2c: "~ deals 1 damage to any target, 2 damage to another target, and 3 damage to a third target." (Cone of Flame), "… 2 damage to target creature, 3 damage to another target
  creature, and 4 damage to a third target creature. If a creature dealt damage this way would die this turn, exile it instead." (Serpentine Spike): three targets, each different from the others
  (the rulings: no cast without three different legal targets); one damage instruction for each, in order.
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
from tests.test_rules_wave34b_activated import settle
from tests.wave9c_kit import build, check, life, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave50e_three_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w50e", number=f"T{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_the_cards_are_full(cards):
    for name in ("Cone of Flame", "Serpentine Spike"):
        assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_cone_of_flame_deals_one_two_and_three_to_three_targets(cards):
    s = build(cards, ["Cone of Flame"], ["Grizzly Bears", "Hill Giant"])
    bears = put(s, "Grizzly Bears", "p2")
    giant = put(s, "Hill Giant", "p2")
    mana(s, R=5)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Cone of Flame").id, targets=["p2", bears.id, giant.id], target_counts=[1, 1, 1])
    settle(s)
    assert life(s, "p2") == 39 and s.state.cards[bears.id].zone == "p2:graveyard" and s.state.cards[giant.id].zone == "p2:graveyard"
    check(s)


def test_cone_of_flame_needs_three_different_targets(cards):
    s = build(cards, ["Cone of Flame"])
    mana(s, R=5)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Cone of Flame").id, targets=["p2", "p2", "p1"], target_counts=[1, 1, 1])
    check(s)


def test_serpentine_spike_deals_two_three_and_four_and_exiles_what_dies(cards):
    s = build(cards, ["Serpentine Spike"], ["Grizzly Bears", "Hill Giant", "Mulldrifter"])
    bears = put(s, "Grizzly Bears", "p2")
    giant = put(s, "Hill Giant", "p2")
    drifter = put(s, "Mulldrifter", "p2")
    mana(s, R=7)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Serpentine Spike").id, targets=[bears.id, giant.id, drifter.id], target_counts=[1, 1, 1])
    settle(s)
    assert {s.state.cards[c.id].zone for c in (bears, giant, drifter)} == {"p2:exile"}  # (2, 3 and 4 damage: all lethal; exiled instead of dying)
    check(s)
