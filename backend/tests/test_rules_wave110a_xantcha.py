"""Wave 110A: Xantcha, Sleeper Agent: enters under an opponent's control (110.2), anyone may activate it (602.2) and its controller loses the life, and it can't
attack its owner or planeswalkers its owner controls (508.1b)."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30p_combat import attack, to_phase
from tests.wave110c_kit import answer, build, check, life, make_db, mana, real

EXTRA = [real("Xantcha, Sleeper Agent", "{2}", 2, "Legendary Artifact Creature — Phyrexian Assassin",
              "Xantcha enters under the control of an opponent of your choice.\nXantcha attacks each combat if able and can't attack its owner or planeswalkers its owner "
              "controls.\n{3}: Xantcha's controller loses 2 life and you draw a card. Any player may activate this ability.", ("2", "2"), "")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Xantcha, Sleeper Agent")).level == "FULL"


def _cast(cards):
    s = build(cards, ["Xantcha, Sleeper Agent"])
    mana(s, "p1", C=2)
    from tests.wave110c_kit import cast

    cast(s, "Xantcha, Sleeper Agent")
    answer(s)
    x = next(c for c in s.state.cards.values() if c.name == "Xantcha, Sleeper Agent")
    return s, x


def _ability(s, x):
    from app.rules.plan import Plan

    return next(a.index for a in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[x.id]).abilities if a.kind == "activated")


def test_enters_under_the_opponents_control_and_anyone_may_activate(cards):
    s, x = _cast(cards)
    assert x.zone == "p2:battlefield" and s.state.cards[x.id].owner == "p1"
    hand = len(s.state.zones["p1:hand"])
    mana(s, "p1", C=3)
    act(s, "p1", type="activate_ability", card_id=x.id, ability=_ability(s, x))
    answer(s)
    assert life(s, "p2") == 38 and life(s, "p1") == 40 and len(s.state.zones["p1:hand"]) == hand + 1  # (its controller loses, the activator draws)
    check(s)


def test_the_controller_may_activate_it_too(cards):
    s, x = _cast(cards)
    to_phase(s, "main1", 2)
    mana(s, "p2", C=3)
    hand = len(s.state.zones["p2:hand"])
    act(s, "p2", type="activate_ability", card_id=x.id, ability=_ability(s, x))
    answer(s)
    assert life(s, "p2") == 38 and len(s.state.zones["p2:hand"]) == hand + 1


def test_cannot_attack_its_owner(cards):
    s, x = _cast(cards)
    s.state.rules.controlled_since[x.id].turn = 0
    to_phase(s, "declare_attackers", 2)
    with pytest.raises(ActionError, match="can.t attack Alice"):
        attack(s, (x, "p1"), pid="p2")
