"""Wave 110N: Bane, Lord of Darkness (608.2d the opponent answers, 603.10a the dead creature's toughness as it last existed)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

BANE, SMALL, MID, BIGC = "Bane, Lord of Darkness", "Tiny Squire", "Mid Squire", "Large Squire"
EXTRA = [
    real(BANE, "{3}{B}", 4, "Legendary Creature — Phyrexian Human",
         "As long as your life total is less than or equal to half your starting life total, Bane has indestructible.\nWhenever another nontoken creature you control dies, "
         "target opponent may have you draw a card. If they don't, you may put a creature card with equal or lesser toughness from your hand onto the battlefield.", ("4", "4"), "B"),
    real(SMALL, "{G}", 1, "Creature — Human", "", ("1", "1"), "G"),
    real(MID, "{1}{G}", 2, "Creature — Human", "", ("2", "2"), "G"),
    real(BIGC, "{3}{G}", 4, "Creature — Human", "", ("4", "4"), "G"),
]


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, EXTRA)


test_full = full_test([BANE])


def pick(s, *ids):
    """Answer the open decision with exactly these options (no more decisions are answered)."""
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(ids))


def kill_bears(cards):
    s = build(cards, [BANE, "Grizzly Bears", "Murder", SMALL, MID, BIGC])
    put(s, BANE)
    bears = put(s, "Grizzly Bears")
    for n in (SMALL, MID, BIGC):
        to_hand(s, n)
    hand = len(s.state.zones["p1:hand"])
    mana(s, "p1", B=3)
    cast(s, "Murder", [bears.id], pay=False)
    return s, hand


def test_the_opponent_may_have_you_draw_instead(cards):
    s, hand = kill_bears(cards)
    answer(s, "p2", "pay")
    assert len(s.state.zones["p1:hand"]) == hand + 1 and zone_of(s, MID) == "p1:hand"
    check(s)


@pytest.mark.parametrize(("chosen", "where"), [(SMALL, "p1:battlefield"), (MID, "p1:battlefield")])
def test_if_they_dont_a_creature_of_equal_or_lesser_toughness_may_enter(cards, chosen, where):
    s, hand = kill_bears(cards)
    pick(s, "p2")
    pick(s, "decline")
    d = s.state.rules.decision
    assert d is not None and {s.state.cards[o.card_id].name for o in d.options} == {SMALL, MID}  # toughness 1 and 2, not the 4/4
    pick(s, next(o.id for o in d.options if s.state.cards[o.card_id].name == chosen))
    answer(s)
    assert zone_of(s, chosen) == where and len(s.state.zones["p1:hand"]) == hand - 1
    check(s)


def test_if_they_dont_you_may_put_nothing(cards):
    s, hand = kill_bears(cards)
    pick(s, "p2")
    pick(s, "decline")
    pick(s)
    answer(s)
    assert len(s.state.zones["p1:hand"]) == hand and zone_of(s, BIGC) == "p1:hand"
    check(s)
