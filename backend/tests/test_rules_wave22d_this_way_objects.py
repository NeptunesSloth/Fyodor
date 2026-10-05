"""Wave 22D: the objects an earlier instruction moved, "this way" (CR 2026-09-25). Real Oracle text; replay and save/load checked.

* 400.7j / 608.2d: "return a creature card put into a graveyard this way to the battlefield under your control" - one of the new
  objects the destruction made in the graveyards, chosen as the spell resolves.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana, pass_until_stack_empty
from tests.test_rules_wave9b_exile_permission import answer, build, find, put, roundtrip
from tests.test_rules_wave12a_counters_keywords import real

EXTRA = [
    real("Necromantic Selection", "{4}{B}{B}", 6, "Sorcery",
         "Destroy all creatures, then return a creature card put into a graveyard this way to the battlefield under your control. It's a black Zombie in addition to its other colors and types. Exile Necromantic Selection.",
         None, "B"),
    real("Probe Two", "{1}{G}", 2, "Creature — Beast", "", ("2", "2"), "G"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_coverage_full(cards):
    assert coverage.of_card_data(cards.resolve("Necromantic Selection")).level == "FULL"


def test_necromantic_selection_returns_one_of_the_creatures_it_destroyed(cards):
    s = build(cards, p1=("Necromantic Selection", "Probe Two"), p2=("Ambush Viper",))
    put(s, "Probe Two", "battlefield")
    viper = put(s, "Ambush Viper", "battlefield", pid="p2")
    spell = put(s, "Necromantic Selection", "hand")
    mana(s, B=2, C=4)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    assert {s.state.cards[o.id].name for o in d.options} == {"Probe Two", "Ambush Viper"}  # both were put into a graveyard this way
    answer(s, pick=viper.id)
    back = s.state.cards[viper.id]
    assert back.zone == "p1:battlefield" and back.controller == "p1"  # under your control (its owner is Bob)
    from app.rules.plan import Plan

    ch = Plan(s.state, "p1", s.cards, None).ch(back)
    assert "Zombie" in ch.subtypes and "B" in ch.colors and "Snake" in ch.subtypes  # "in addition to its other colors and types"
    assert s.state.cards[find(s, "Probe Two").id].zone == "p1:graveyard"
    assert s.state.cards[find(s, "Necromantic Selection").id].zone == "p1:exile"
    roundtrip(s)
