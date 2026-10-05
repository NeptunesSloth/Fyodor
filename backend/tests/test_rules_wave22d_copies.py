"""Wave 22D: copies with exceptions, several at once (CR 707.9, 707.2, 111.3, 603.7; 2026-09-25). Real Oracle text; replay and save/load checked.

* 707.9 / 707.2: "create a token that's a copy of each of any number of target creatures, except it has haste" - one token for each chosen creature.
* 603.7: "Exile those tokens at the beginning of the next end step" - the delayed trigger acts on the tokens this resolution made, not on anything else.
* 601.2f / strive: {2}{R} more for each target beyond the first.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana, pass_until_stack_empty, run_until
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave9b_exile_permission import build, find, put, roundtrip

EXTRA = [
    real("Twinflame", "{1}{R}", 2, "Sorcery",
         "Strive — This spell costs {2}{R} more to cast for each target beyond the first.\nChoose any number of target creatures you control. For each of them, create a token that's a copy of that creature, except it has haste. Exile those tokens at the beginning of the next end step.",
         None, "R"),
    real("Probe Two", "{1}{G}", 2, "Creature — Beast", "", ("2", "2"), "G"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_coverage_full(cards):
    assert coverage.of_card_data(cards.resolve("Twinflame")).level == "FULL"


def battlefield(s, name):
    return [c for c in s.state.cards.values() if c.name == name and c.zone.endswith(":battlefield")]


def test_twinflame_copies_each_chosen_creature_with_haste_and_exiles_only_those_tokens_at_the_end_step(cards):
    s = build(cards, p1=("Twinflame", "Probe Two", "Ambush Viper"))
    two, viper = put(s, "Probe Two", "battlefield"), put(s, "Ambush Viper", "battlefield")
    spell = put(s, "Twinflame", "hand")
    mana(s, R=2, C=3)  # {1}{R} plus {2}{R} for the second target
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[two.id, viper.id], target_counts=[2])
    pass_until_stack_empty(s)
    tokens = [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]
    assert sorted(t.name for t in tokens) == ["Ambush Viper", "Probe Two"]  # a token copy of each chosen creature
    plan = Plan(s.state, "p1", s.cards, None)
    assert all("haste" in plan.ch(t).keywords for t in tokens)  # 707.9: the exception; the originals don't have it
    assert "haste" not in plan.ch(s.state.cards[two.id]).keywords
    roundtrip(s)
    assert len(s.state.rules.delayed) == 1  # one delayed trigger for the "next end step", acting on both tokens
    run_until(s, lambda s: s.state.turn.number == 2)  # through this turn's end step (603.7: the next one that begins)
    pass_until_stack_empty(s)
    assert not [c for c in s.state.cards.values() if c.is_token and c.zone.endswith(":battlefield") and c.name in ("Probe Two", "Ambush Viper")]
    assert s.state.cards[two.id].zone == "p1:battlefield" and s.state.cards[viper.id].zone == "p1:battlefield"  # the originals stay
    roundtrip(s)
