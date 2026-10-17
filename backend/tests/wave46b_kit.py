"""Shared helpers of the wave 46B scenario tests (real Oracle text of tests/fixtures/wave46b_cards.json, from data/cards.sqlite)."""

from __future__ import annotations

import json
from pathlib import Path

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.wave9c_kit import card_named

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave46b_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w46b", number=f"B{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


def make_repo(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))


def zone(s, name, pid="p1"):
    return s.state.cards[card_named(s, name, pid).id].zone
