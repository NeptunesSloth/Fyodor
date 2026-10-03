"""Wave 13E: "Whenever you roll one or more dice, …" (Brazen Dwarf, Feywild Trickster, Vrondiss, Rage of Ancients), researched
against CR 2026-09-25 (706; 603.2: the trigger event is the roll, once however many dice). Real Oracle text, replay and save/load.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana
from tests.test_rules_wave12a_counters_keywords import EXTRA as DICE
from tests.test_rules_wave12a_counters_keywords import answer, real, rolls
from tests.wave9c_kit import build, check, put, to_hand

EXTRA = [c for c in DICE if c["name"] in ("Reckless Endeavor", "Dissatisfied Customer")] + [
    real("Brazen Dwarf", "{2}{R}", 3, "Creature — Dwarf Berserker",
         "Whenever you roll one or more dice, this creature deals 1 damage to each opponent.", ("2", "2"), "R"),
    real("Feywild Trickster", "{1}{U}", 2, "Creature — Faerie Dragon Wizard",
         "Flying\nWhenever you roll one or more dice, create a 1/1 blue Faerie Dragon creature token with flying.", ("1", "1"), "U"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", ["Brazen Dwarf", "Feywild Trickster"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_brazen_dwarf_triggers_once_for_a_roll_of_two_dice(cards, monkeypatch):
    rolls(monkeypatch, 3, 7)
    s = build(cards, ["Brazen Dwarf", "Reckless Endeavor"], [])
    put(s, "Brazen Dwarf")
    spell = to_hand(s, "Reckless Endeavor")
    mana(s, "p1", R=2, C=5)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    answer(s, "1")
    assert s.state.players["p2"].life == 39  # one trigger for the roll of two dice (603.2)
    check(s)


def test_feywild_trickster_makes_a_token_when_its_controller_rolls(cards, monkeypatch):
    rolls(monkeypatch, 2)
    s = build(cards, ["Feywild Trickster", "Dissatisfied Customer"], [])
    put(s, "Feywild Trickster")
    cust = to_hand(s, "Dissatisfied Customer")
    mana(s, "p1", B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=cust.id)
    answer(s)
    assert [c.name for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Faerie Dragon"] == ["Faerie Dragon"]
    check(s)
