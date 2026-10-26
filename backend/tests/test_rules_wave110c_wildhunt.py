"""Wave 110C: Master of the Wild Hunt (120.3, 608.2h, 701.14a-like simultaneous damage): the Wolves tapped this way (not the ones already tapped) deal damage equal to their power to the
target creature; then that creature deals damage equal to its power divided as ITS controller chooses among those Wolves (a share may be 0)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110c_kit import check, make_db, put, real
from tests.wave110d_kit import ability, settle

TEXT = ("At the beginning of your upkeep, create a 2/2 green Wolf creature token.\n{T}: Tap all untapped Wolf creatures you control. Each Wolf tapped this way deals damage equal to its "
        "power to target creature. That creature deals damage equal to its power divided as its controller chooses among any number of those Wolves.")
EXTRA = [real("Master of the Wild Hunt", "{2}{G}{G}", 4, "Creature — Human Shaman", TEXT, ("2", "2"), "G"),
         real("Wolf Alpha", "{1}", 1, "Creature — Wolf", "", ("2", "5"), ""), real("Wolf Beta", "{1}", 1, "Creature — Wolf", "", ("3", "5"), ""),
         real("Wolf Gamma", "{1}", 1, "Creature — Wolf", "", ("4", "5"), ""), real("Stone Giant", "{1}", 1, "Creature — Giant", "", ("3", "7"), "")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Master of the Wild Hunt")).level == "FULL"


def board(cards):
    s = build(cards, ["Master of the Wild Hunt", "Wolf Alpha", "Wolf Beta", "Wolf Gamma"], ["Stone Giant"])
    master = put(s, "Master of the Wild Hunt")
    s.state.rules.controlled_since[master.id].turn = 0
    wolves = [put(s, n) for n in ("Wolf Alpha", "Wolf Beta", "Wolf Gamma")]
    giant = put(s, "Stone Giant", "p2")
    return s, master, wolves, giant


def activate(s, master, giant):
    """Activate and resolve up to the division (settle would answer it)."""
    act(s, "p1", type="activate_ability", card_id=master.id, ability=ability(s, master, "{T}"), targets=[giant.id])
    while s.state.rules.decision is None and s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")


def divide(s, *amounts):
    d = s.state.rules.decision
    assert d.kind == "divide" and d.player == "p2"  # (the target's controller divides)
    act(s, d.player, type="choose", decision_id=d.id, amounts=list(amounts))
    settle(s)


def test_only_the_wolves_tapped_this_way_deal_damage_and_the_controller_divides(cards):
    s, master, (alpha, beta, gamma), giant = board(cards)
    act(s, "p1", type="tap", card_ids=[gamma.id])  # (already tapped: neither tapped this way nor dealing damage)
    activate(s, master, giant)
    assert s.state.cards[giant.id].damage == 5 and s.state.cards[master.id].tapped  # 2 + 3, not Gamma's 4
    divide(s, 1, 2)  # Alpha 1, Beta 2 of the Giant's 3 power
    assert (s.state.cards[alpha.id].damage, s.state.cards[beta.id].damage, s.state.cards[gamma.id].damage) == (1, 2, 0)
    check(s)


def test_a_share_may_be_zero(cards):
    s, master, (alpha, beta, gamma), giant = board(cards)
    activate(s, master, giant)
    divide(s, 0, 0, 3)
    assert (s.state.cards[alpha.id].damage, s.state.cards[beta.id].damage, s.state.cards[gamma.id].damage) == (0, 0, 3)
    check(s)


def test_a_single_wolf_takes_it_all_without_a_choice(cards):
    s, master, (alpha, beta, gamma), giant = board(cards)
    act(s, "p1", type="tap", card_ids=[beta.id, gamma.id])
    activate(s, master, giant)
    assert s.state.rules.decision is None and s.state.cards[giant.id].damage == 2 and s.state.cards[alpha.id].damage == 3
    check(s)
