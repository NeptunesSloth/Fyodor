"""Shared helpers of the wave 46C scenario tests: the real-Oracle fixture cards (tests/fixtures/wave46c_cards.json, from data/cards.sqlite) and the 43B table helpers."""

from __future__ import annotations

import json
from pathlib import Path

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.wave43b_kit import cast, life, names_in, tapped  # noqa: F401  (re-exported for the 46C tests)

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave46c_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w46c", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
SUPPORT = ("Hill Giant", "Grizzly Bears", "Shock", "Shivan Dragon", "Rishkar, Peema Renegade", "Skinrender")  # (cards the scenarios need, not under test)
FULL = [c["name"] for c in DATA if c["name"] not in SUPPORT]


def open_cards(settings):
    """The card repository of a scenario (a generator for each module's own ``cards`` fixture): the fixture cards and the real-Oracle ones."""
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()
