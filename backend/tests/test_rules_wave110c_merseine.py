"""Wave 110C: Merseine. 602.2 / 602.2a ("Only the controller of the enchanted creature may activate this ability": that player activates and pays),
107.3 (X is 0 off the stack), 122.1 (net counters), 502.3 (doesn't untap while it has a net counter)."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.wave110c_kit import answer, build, card_named, cast, check, make_db, mana, put, real
from tests.wave110d_kit import ability

MERSEINE = ("Enchant creature\nThis Aura enters with three net counters on it.\nEnchanted creature doesn't untap during its controller's untap step "
            "if this Aura has a net counter on it.\nPay enchanted creature's mana cost: Remove a net counter from this Aura. Only the controller of the "
            "enchanted creature may activate this ability.")
EXTRA = [real("Merseine", "{2}{U}{U}", 4, "Enchantment — Aura", MERSEINE, None, "U"),
         real("Test Giant", "{2}{R}", 3, "Creature — Giant", "", ("3", "3"), "R"),
         real("Test Xer", "{X}{R}", 1, "Creature — Giant", "", ("1", "1"), "R")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Merseine")).level == "FULL"


def setup(cards, victim="Test Giant"):
    s = build(cards, ["Merseine"], [victim], islands=10)
    v = put(s, victim, "p2")
    mana(s, U=4)
    cast(s, "Merseine", [v.id])
    answer(s)
    return s, card_named(s, "Merseine"), v


def nets(s):
    return card_named(s, "Merseine").counters.get("net", 0)


def test_enters_with_three_and_controller_pays_the_creatures_cost(cards):
    s, m, _ = setup(cards)
    assert nets(s) == 3
    s.state.rules.priority = "p2"
    mana(s, "p2", R=1, C=2)
    act(s, "p2", type="activate_ability", card_id=m.id, ability=ability(s, m, "Pay enchanted"))
    answer(s)
    assert nets(s) == 2
    check(s)


def test_aura_controller_cannot_activate(cards):
    s, m, _ = setup(cards)
    mana(s, R=1, C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=m.id, ability=ability(s, m, "Pay enchanted"))
    assert nets(s) == 3


def test_cannot_pay_without_the_mana(cards):
    s, m, _ = setup(cards)
    s.state.rules.priority = "p2"
    mana(s, "p2", R=1)
    with pytest.raises(ActionError):
        act(s, "p2", type="activate_ability", card_id=m.id, ability=ability(s, m, "Pay enchanted"))


def test_x_in_the_creatures_cost_is_zero(cards):  # 107.3: {X}{R} costs {R}
    s, m, _ = setup(cards, "Test Xer")
    s.state.rules.priority = "p2"
    mana(s, "p2", R=1)
    act(s, "p2", type="activate_ability", card_id=m.id, ability=ability(s, m, "Pay enchanted"))
    answer(s)
    assert nets(s) == 2
