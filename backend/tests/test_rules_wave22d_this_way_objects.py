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
    real("Probe Four", "{3}{G}", 4, "Creature — Beast", "", ("4", "4"), "G"),
    real("Pure Reflection", "{2}{W}", 3, "Enchantment",
         "Whenever a player casts a creature spell, destroy all Reflections. Then that player creates an X/X white Reflection creature token, where X is the mana value of that spell.",
         None, "W"),
    real("Random Encounter", "{4}{R}{R}", 6, "Sorcery",
         "Shuffle your library, then mill four cards. Put each creature card milled this way onto the battlefield. They gain haste. At the beginning of the next end step, return those creatures to their owner's hand.\nFlashback {6}{R}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
         None, "R"),
    real("Glacial Dragonhunt", "{U}{R}", 2, "Sorcery",
         "Draw a card, then you may discard a card. When you discard a nonland card this way, Glacial Dragonhunt deals 3 damage to target creature.\nHarmonize {4}{U}{R} (You may cast this card from your graveyard for its harmonize cost. You may tap a creature you control to reduce that cost by {X}, where X is its power. Then exile this spell.)",
         None, "UR"),
    real("Severance Priest", "{W}{B}{G}", 3, "Creature — Djinn Cleric",
         "Deathtouch\nWhen this creature enters, target opponent reveals their hand. You may choose a nonland card from it. If you do, exile that card.\nWhen this creature leaves the battlefield, the exiled card's owner creates an X/X white Spirit creature token, where X is the mana value of the exiled card.",
         ("3", "3"), "BGW"),
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


@pytest.mark.parametrize("name", ["Necromantic Selection", "Pure Reflection", "Random Encounter", "The Ancient One"])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_pure_reflection_makes_an_x_x_token_for_the_player_who_cast_the_spell(cards):
    from tests.wave9c_kit import pt

    s = build(cards, p1=("Pure Reflection", "Probe Two", "Probe Four"))
    put(s, "Pure Reflection", "battlefield")
    for name, size in (("Probe Two", 2), ("Probe Four", 4)):
        c = put(s, name, "hand")
        mana(s, G=1, C=size - 1)
        act(s, "p1", type="cast_spell", card_id=c.id)
        pass_until_stack_empty(s)
        reflections = [x for x in s.state.cards.values() if x.name == "Reflection" and x.zone == "p1:battlefield"]
        assert len(reflections) == 1 and pt(s, "Reflection") == (size, size)  # "destroy all Reflections", then one the size of that spell
        roundtrip(s)


def test_random_encounter_puts_each_creature_milled_this_way_onto_the_battlefield_and_returns_them_at_the_end_step(cards):
    from tests.test_rules_effects import run_until

    s = build(cards, p1=("Random Encounter", "Probe Two", "Probe Four"))
    spell = put(s, "Random Encounter", "hand")
    mana(s, R=2, C=4)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    pass_until_stack_empty(s)
    on_field = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name.startswith("Probe")]
    in_graveyard = [c for c in s.state.cards.values() if c.zone == "p1:graveyard" and c.name != "Random Encounter"]
    assert len(on_field) + len(in_graveyard) == 4  # four cards milled: the creatures went on, the rest stayed
    assert all(c.name.startswith("Probe") for c in on_field) and all(not c.name.startswith("Probe") for c in in_graveyard)
    roundtrip(s)
    run_until(s, lambda s: s.state.turn.number == 2)  # through the end step: those creatures return to their owner's hand
    assert all(s.state.cards[c.id].zone == "p1:hand" for c in on_field if c.id in s.state.cards)
    roundtrip(s)


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
