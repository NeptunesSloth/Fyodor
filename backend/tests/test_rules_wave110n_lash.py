"""Wave 110N: Thought Lash (702.24a cumulative upkeep paid by exiling cards, 603.2 the "doesn't pay" trigger)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

LASH = "Thought Lash"
EXTRA = [real(LASH, "{U}", 1, "Enchantment",
              "Cumulative upkeep—Exile the top card of your library. (At the beginning of your upkeep, put an age counter on this permanent, then sacrifice it unless you pay its "
              "upkeep cost for each age counter on it.)\nWhen a player doesn't pay this enchantment's cumulative upkeep, that player exiles all cards from their library.\n"
              "Exile the top card of your library: Prevent the next 1 damage that would be dealt to you this turn.", None, "U")]


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, EXTRA)


test_full = full_test([LASH])


def upkeep(s, turn=3):
    """Alice's upkeep of her next turn, with the cumulative upkeep trigger on the stack."""
    act(s, "p1", type="set_stops", own=STEPS + ["upkeep"], others=STEPS + ["upkeep"], smart_pass=False)
    until(s, lambda s: s.state.turn.number == turn and s.state.turn.phase == "upkeep" and s.state.rules.priority == "p1")


def to_stack_end(s):
    """Pass priority until the stack is empty (or a decision opens), returning the decision."""
    for _ in range(20):
        if s.state.rules.decision is not None or not s.state.zones.get("stack"):
            return s.state.rules.decision
        act(s, s.state.rules.priority, type="pass_priority")


def lib(s):
    return len(s.state.zones["p1:library"])


def exiled(s):
    return len(s.state.zones.get("p1:exile", []))


def test_paying_exiles_one_card_for_each_age_counter(cards):
    s = build(cards, [LASH])
    lash = put(s, LASH)
    before = lib(s)
    upkeep(s, 3)
    answer(s, "pay")
    assert s.state.cards[lash.id].counters.get("age") == 1 and exiled(s) == 1
    upkeep(s, 5)
    answer(s, "pay")
    assert s.state.cards[lash.id].counters.get("age") == 2 and exiled(s) == 3
    assert zone_of(s, LASH) == "p1:battlefield" and lib(s) == before - 3 - 1  # (one draw so far, three exiled)
    check(s)


def test_not_paying_sacrifices_it_and_exiles_the_whole_library(cards):
    s = build(cards, [LASH])
    put(s, LASH)
    upkeep(s, 3)
    answer(s, "decline")
    assert zone_of(s, LASH) == "p1:graveyard" and lib(s) == 0
    check(s)


def test_a_library_too_small_to_pay_cannot_pay(cards):
    s = build(cards, [LASH])
    put(s, LASH)
    for c in list(s.state.zones["p1:library"]):
        act(s, "p1", type="move", card_ids=[c], to={"player": "p1", "zone": "graveyard"})
    upkeep(s, 3)
    d = to_stack_end(s)
    assert d is None and zone_of(s, LASH) == "p1:graveyard"  # nothing could be paid: no question
    check(s)
