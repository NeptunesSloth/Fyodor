"""Wave 22D: a static permission over "cards exiled with ~" (CR 607.2a, 611.3a, 400.7; 2026-09-25). Real Oracle text; replay and save/load checked.

* 607.2a: only the cards the linked exiling ability put in exile (Theater of Horrors' upkeep trigger) - not any other card in exile - and only while
  each is still that object there (400.7).
* 611.3a: "During your turn, if an opponent lost life this turn" is checked whenever the cast is offered.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from app.rules.casting import castable
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana, pass_until_stack_empty, run_until
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave9b_exile_permission import build, find, put, roundtrip

EXTRA = [
    real("Theater of Horrors", "{1}{B}{R}", 3, "Enchantment",
         "At the beginning of your upkeep, exile the top card of your library.\nDuring your turn, if an opponent lost life this turn, you may play lands and cast spells from among cards exiled with this enchantment.\n{3}{R}: This enchantment deals 1 damage to target opponent or planeswalker.",
         None, "BR"),
    real("Probe Rock", "{3}", 3, "Artifact", "", None),
    real("Probe Burst", "{R}", 1, "Instant", "Probe Burst deals 1 damage to any target.", None, "R"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def test_coverage_full(cards):
    assert coverage.of_card_data(cards.resolve("Theater of Horrors")).level == "FULL"


def test_theater_of_horrors_lets_you_cast_the_exiled_card_only_when_an_opponent_lost_life(cards):
    s = build(cards, p1=("Theater of Horrors", "Probe Rock", "Probe Burst"))
    put(s, "Theater of Horrors", "battlefield")
    rock = put(s, "Probe Rock", "library", position="top")
    other = find(s, "Probe Burst")
    put(s, "Probe Burst", "exile")  # an unrelated card in exile: not "exiled with" the enchantment
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")  # Alice's next turn: the upkeep exiled the top card
    assert s.state.cards[rock.id].zone == "p1:exile"
    assert not castable(s.state, "p1", s.state.cards[rock.id], cards)  # no opponent lost life yet this turn
    assert not castable(s.state, "p1", s.state.cards[other.id], cards)  # (and that card is never covered)
    burst = put(s, "Probe Burst", "hand")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=burst.id, targets=["p2"])
    pass_until_stack_empty(s)
    mana(s, C=3)
    assert castable(s.state, "p1", s.state.cards[rock.id], cards)  # an opponent lost life this turn
    roundtrip(s)
    act(s, "p1", type="cast_spell", card_id=rock.id)
    pass_until_stack_empty(s)
    assert s.state.cards[rock.id].zone == "p1:battlefield"
    roundtrip(s)
