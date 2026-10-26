"""Helpers of the wave 110N scenario tests: the wave 110A kit, with the test's own real Oracle text cards added to the card database."""

from __future__ import annotations

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import fixture_cards
from tests.wave110a_kit import *  # noqa: F403
from tests.wave110a_kit import EXTRA as _EXTRA_110A


def open_repo_with(settings, extra):
    """The fixture cards and ``extra`` (tests.test_rules_wave12a_counters_keywords.real) in a test card database."""
    settings.ensure_dirs()
    build_database([*fixture_cards(), *_EXTRA_110A, *extra], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()
