"""Wave 110H session 8: one-card builds on real Oracle text (each scenario checks replay and a save/load round trip).

* Darigaaz Reincarnated: dying is replaced by exile with three egg counters (614.1a, 122.1); at each of its owner's upkeeps one comes off (603.4), and with none left it returns (400.7).
"""
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110h_s5 import answer
from tests.wave9c_kit import build, check, mana, put, to_hand
from tests.wave110j_kit import now, to_phase

EXTRA = [
    real("Darigaaz Reincarnated", "{4}{B}{R}{G}", 7, "Legendary Creature — Dragon",
         "Flying, trample, haste\nIf Darigaaz would die, instead exile it with three egg counters on it.\nAt the beginning of your upkeep, if this card is exiled with an egg "
         "counter on it, remove an egg counter from it. Then if this card has no egg counters on it, return it to the battlefield.", ("7", "7"), "BRG"),
    real("Murder", "{1}{B}{B}", 3, "Instant", "Destroy target creature.", None, "B"),
]
NAMES = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_darigaaz_exiles_with_egg_counters_and_returns_on_the_third_upkeep(cards):
    """Destroyed: exiled with three egg counters (not dead); the owner's upkeeps (not the opponent's) remove one each; the third return puts it on the battlefield."""
    s = build(cards, ["Darigaaz Reincarnated", "Murder"])
    dari = put(s, "Darigaaz Reincarnated")
    mana(s, B=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Murder").id, targets=[dari.id])
    answer(s)
    assert now(s, dari).zone == "p1:exile" and now(s, dari).counters == {"egg": 3}
    to_phase(s, "main1", turn=3)
    assert now(s, dari).zone == "p1:exile" and now(s, dari).counters == {"egg": 2}  # (turn 2 was p2's upkeep: no tick)
    to_phase(s, "main1", turn=5)
    assert now(s, dari).zone == "p1:exile" and now(s, dari).counters == {"egg": 1}
    to_phase(s, "main1", turn=7)
    assert now(s, dari).zone == "p1:battlefield" and not now(s, dari).counters
    check(s)
