"""Wave 110C: Venom, Lethal Protector (603.1 attack trigger; optional sacrifice, "If you do": draw X, then put a permanent card with mana value X or less from hand, X = the sacrificed creature's mana value, 608.2c)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30p_combat import attack, to_phase
from tests.wave110c_kit import answer, build, check, make_db, put, real, to_hand

EXTRA = [real("Venom, Lethal Protector", "{1}{R}{G}{B}", 4, "Legendary Creature — Symbiote Alien Hero",
              "Menace, trample, haste\nWhenever Venom attacks, you may sacrifice another creature. If you do, draw X cards, then you may put a permanent card "
              "with mana value X or less from your hand onto the battlefield, where X is the sacrificed creature's mana value.", ("5", "5"), "BRG")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Venom, Lethal Protector")).level == "FULL"


def test_sacrifice_draws_and_puts(cards):
    s = build(cards, ["Venom, Lethal Protector", "Grizzly Bears", "Llanowar Elves", "Forest"])
    venom, bears = put(s, "Venom, Lethal Protector"), put(s, "Grizzly Bears")
    elves = to_hand(s, "Llanowar Elves")
    to_phase(s, "declare_attackers", 1)
    hand = len(s.state.zones["p1:hand"])
    attack(s, (venom, "p2"))
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["pay"])
    answer(s)
    assert s.state.cards[bears.id].zone == "p1:graveyard"
    assert len(s.state.zones["p1:hand"]) == hand + 2 - 1  # drew 2 (Grizzly Bears' mana value), put the Elves (mana value 1) onto the battlefield
    assert s.state.cards[elves.id].zone == "p1:battlefield"
    check(s)


def test_declining_does_nothing(cards):
    s = build(cards, ["Venom, Lethal Protector", "Grizzly Bears"])
    venom, bears = put(s, "Venom, Lethal Protector"), put(s, "Grizzly Bears")
    to_phase(s, "declare_attackers", 1)
    hand = len(s.state.zones["p1:hand"])
    attack(s, (venom, "p2"))
    answer(s, "decline")
    assert s.state.cards[bears.id].zone == "p1:battlefield" and len(s.state.zones["p1:hand"]) == hand
    check(s)
