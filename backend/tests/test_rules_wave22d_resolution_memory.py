"""Wave 22D: resolution memory and linked objects (CR 2026-09-25). Real Oracle text; every scenario checks the replay and a save and a load.

* 608.2h / 107.3c: "where X is 2 plus the sacrificed creature's mana value" - a spell's additional-cost sacrifice is read as the creature last existed.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import answer, real
from tests.wave9c_kit import build, card_named, check, put, to_hand

EXTRA = [
    real("Eldritch Evolution", "{1}{G}{G}", 3, "Sorcery",
         "As an additional cost to cast this spell, sacrifice a creature.\nSearch your library for a creature card with mana value X or less, where X is 2 plus the sacrificed creature's mana value. Put that card onto the battlefield, then shuffle. Exile Eldritch Evolution.",
         None, "G"),
    real("Probe Four", "{3}{G}", 4, "Creature — Beast", "", ("4", "4"), "G"),
    real("Probe Five", "{4}{G}", 5, "Creature — Beast", "", ("5", "5"), "G"),
    real("Probe Two", "{1}{G}", 2, "Creature — Beast", "", ("2", "2"), "G"),
]

NAMES = ["Eldritch Evolution"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def zone(s, name, pid="p1"):
    return s.state.cards[card_named(s, name, pid).id].zone


def test_eldritch_evolution_finds_up_to_two_more_than_the_sacrificed_creature(cards):
    s = build(cards, ["Eldritch Evolution", "Probe Two", "Probe Four", "Probe Five"], [])
    put(s, "Probe Two")
    spell = to_hand(s, "Eldritch Evolution")
    act(s, "p1", type="add_mana", player="p1", mana={"G": 3})
    act(s, "p1", type="cast_spell", card_id=spell.id)
    assert zone(s, "Probe Two") == "p1:graveyard"  # sacrificed as a cost
    d = None
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.kind != "choose_cost":
            break
        answer(s, limit=1)
    names = {s.state.cards[o.id].name for o in d.options}
    assert "Probe Four" in names and "Probe Five" not in names  # mana value 2 + 2 = 4 or less
    answer(s, card_named(s, "Probe Four").id)
    assert zone(s, "Probe Four") == "p1:battlefield" and zone(s, "Eldritch Evolution") == "p1:exile"
    check(s)
