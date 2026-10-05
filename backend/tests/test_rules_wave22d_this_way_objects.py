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
    real("Probe Rock", "{3}", 3, "Artifact", "", None),
    real("The Ancient One", "{U}{B}", 2, "Legendary Creature — Spirit God",
         "Descend 8 — The Ancient One can't attack or block unless there are eight or more permanent cards in your graveyard.\n{2}{U}{B}: Draw a card, then discard a card. When you discard a card this way, target player mills cards equal to its mana value.",
         ("8", "8"), "BU"),
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


def test_the_ancient_one_mills_by_the_mana_value_of_the_card_discarded_this_way(cards):
    s = build(cards, p1=("The Ancient One", "Probe Rock"))
    one = put(s, "The Ancient One", "battlefield")
    rock = put(s, "Probe Rock", "hand")  # the only card in hand besides the one drawn
    for c in list(s.state.zones["p1:hand"]):
        if c != rock.id:
            act(s, "p1", type="move", card_ids=[c], to={"player": "p1", "zone": "library"})
    mana(s, U=1, B=1, C=2)
    library = len(s.state.zones["p2:library"])
    act(s, "p1", type="activate_ability", card_id=one.id, ability=1)
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[rock.id])  # discard the Rock (mana value 3)
    pass_until_stack_empty(s)
    d = s.state.rules.decision
    assert d is not None  # the reflexive trigger's target: a player
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["p2"])
    pass_until_stack_empty(s)
    assert s.state.cards[rock.id].zone == "p1:graveyard"
    assert len(s.state.zones["p2:library"]) == library - 3  # "cards equal to its mana value": the Rock's 3
    roundtrip(s)
