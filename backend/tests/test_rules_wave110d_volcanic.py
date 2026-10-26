"""Wave 110D: Volcanic Offering is refused again: "which opponent chooses each target" (several opponents) has no CR rule or ruling in data/rules.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave110d_kit import card_db as _kit_db  # noqa: F401

EXTRA = [real("Volcanic Offering", "{4}{R}", 5, "Instant",
              "Destroy target nonbasic land you don't control and target nonbasic land of an opponent's choice you don't control.\n"
              "Volcanic Offering deals 7 damage to target creature you don't control and 7 damage to target creature of an opponent's choice you don't control.",
              None, "R")]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_refused(cards):
    assert coverage.of_card_data(cards.resolve("Volcanic Offering")).level != "FULL"
