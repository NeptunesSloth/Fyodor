"""Helpers of the wave 110N scenario tests: the wave 110A kit, with the test's own real Oracle text cards added to the card database."""

from __future__ import annotations

import json
from pathlib import Path

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.wave110a_kit import *  # noqa: F403
from tests.wave110a_kit import EXTRA as _EXTRA_110A

# real database rows (tests/fixtures/wave110n_cards.json, exported from data/cards.sqlite) for the cards with several faces
_REAL = [card(c["name"], set_code="w110n", number=f"N{i:03d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(json.loads((Path(__file__).parent / "fixtures" / "wave110n_cards.json").read_text("utf-8")))]


def open_repo_with(settings, extra):
    """The fixture cards and ``extra`` (tests.test_rules_wave12a_counters_keywords.real) in a test card database."""
    settings.ensure_dirs()
    build_database([*fixture_cards(), *_EXTRA_110A, *_REAL, *extra], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()
