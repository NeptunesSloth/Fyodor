"""Wave 10C: "At the beginning of your upkeep, if this creature has one or more +1/+1 counters on it, you may remove a +1/+1 counter
from it. If you do, draw a card." (Ingenious Prodigy), researched against CR 2026-09-25.

* 603.4: the intervening "if" is checked as the ability triggers and again as it resolves.
* 118.12: removing the counter is an optional cost paid as it resolves; "If you do" asks whether it was paid.
* 608.2c: the "it" of the sentence after the condition is the object the condition is about (the source).

Every scenario checks the replay and a save/load round trip.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import mana, pass_until_stack_empty
from tests.test_rules_wave9b_exile_permission import build, find, roundtrip

EXTRA = [
    card('Ingenious Prodigy', set_code='tst', number='I01', mana_cost='{X}{U}', cmc=1.0, type_line='Creature — Human Wizard', oracle_text="Skulk (This creature can't be blocked by creatures with greater power.)\nThis creature enters with X +1/+1 counters on it.\nAt the beginning of your upkeep, if this creature has one or more +1/+1 counters on it, you may remove a +1/+1 counter from it. If you do, draw a card.", power='0', toughness='1', colors=['U'], color_identity=['U'], keywords=['Skulk']),  # noqa: E501
]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards() + EXTRA, settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def hand_size(s):
    return len([c for c in s.state.cards.values() if c.zone == "p1:hand"])


def to_next_upkeep_question(s):
    """Pass until Alice is asked the optional payment at her next upkeep."""
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_one" and d.player == "p1":
            return d
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
    raise AssertionError("no upkeep question")


def cast_prodigy(cards, x):
    s = build(cards, p1=("Ingenious Prodigy",))
    c = find(s, "Ingenious Prodigy")
    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "hand"})
    mana(s, U=x + 1)
    act(s, "p1", type="cast_spell", card_id=c.id, x_value=x)
    pass_until_stack_empty(s)
    return s, c


def test_coverage_full(cards):
    assert coverage.of_card_data(cards.resolve("Ingenious Prodigy")).level == "FULL"


def upkeep_answer(cards, pay):
    s, c = cast_prodigy(cards, 2)
    assert s.state.cards[c.id].counters.get("+1/+1") == 2
    d = to_next_upkeep_question(s)
    option = next(o for o in d.options if o.id.startswith("pay") == pay)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[option.id])
    pass_until_stack_empty(s)
    return s, c


def test_remove_a_counter_and_draw_at_upkeep(cards):
    paid, c = upkeep_answer(cards, True)
    declined, d = upkeep_answer(cards, False)
    assert paid.state.cards[c.id].counters.get("+1/+1") == 1  # the counter was the cost
    assert declined.state.cards[d.id].counters.get("+1/+1") == 2  # "you may": declined, nothing removed
    assert hand_size(paid) == hand_size(declined) + 1  # "If you do, draw a card": only when it was paid (118.12)
    roundtrip(paid)
    roundtrip(declined)
