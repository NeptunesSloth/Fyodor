"""Wave 110C: Saw (603.1 attack trigger; the optional payment's cost (cost_payment.Plan.cost_attacker) can't take the attacker or the Equipment itself, "If you do" draws, 608.2c)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30p_combat import attack, to_phase
from tests.wave110c_kit import answer, build, check, make_db, mana, put, real

EXTRA = [real("Saw", "{2}", 2, "Artifact — Equipment",
              "Equipped creature gets +2/+0.\nWhenever equipped creature attacks, you may sacrifice a permanent other than that creature or this Equipment. "
              "If you do, draw a card.\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)", None, "")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Saw")).level == "FULL"


def test_sacrifice_other_permanent_draws(cards):
    s = build(cards, ["Saw", "Grizzly Bears", "Forest"])
    saw, bears, forest = put(s, "Saw"), put(s, "Grizzly Bears"), put(s, "Forest")
    mana(s, "p1", C=2)
    act(s, "p1", type="activate_ability", card_id=saw.id, ability=2, targets=[bears.id])
    answer(s)
    assert s.state.cards[saw.id].attached_to == bears.id
    to_phase(s, "declare_attackers", 3)
    hand = len(s.state.zones["p1:hand"])
    attack(s, (bears, "p2"))
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["pay"])
    assert s.state.rules.decision is None  # only the Forest can pay (neither the attacker nor the Equipment): no choice; before the fix the attacker was offered too
    answer(s)
    assert s.state.cards[forest.id].zone == "p1:graveyard" and len(s.state.zones["p1:hand"]) == hand + 1
    assert s.state.cards[saw.id].zone == "p1:battlefield" and s.state.cards[bears.id].zone == "p1:battlefield"
    check(s)


def test_declining_draws_nothing(cards):
    s = build(cards, ["Saw", "Grizzly Bears", "Forest"])
    saw, bears, forest = put(s, "Saw"), put(s, "Grizzly Bears"), put(s, "Forest")
    mana(s, "p1", C=2)
    act(s, "p1", type="activate_ability", card_id=saw.id, ability=2, targets=[bears.id])
    answer(s)
    to_phase(s, "declare_attackers", 3)
    hand = len(s.state.zones["p1:hand"])
    attack(s, (bears, "p2"))
    answer(s, "decline")
    assert s.state.cards[forest.id].zone == "p1:battlefield" and len(s.state.zones["p1:hand"]) == hand
    check(s)
