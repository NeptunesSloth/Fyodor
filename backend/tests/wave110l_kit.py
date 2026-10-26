"""Shared helpers of the wave 110L scenario tests: real Oracle text cards (tests/fixtures/wave110l_cards.json) on the wave 9C table (Alice p1, Bob p2)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import json
from pathlib import Path

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.wave110a_kit import *

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave110l_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w110l", number=f"L{i:03d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


def open_repo(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()
