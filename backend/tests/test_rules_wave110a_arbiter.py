"""Wave 110A: Leonin Arbiter (614.17 can't search; ruling 2011-01-01: {2} is a special action, per player, lasts the turn, any library, each Arbiter needs its own)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.rules import coverage, prohibitions
from app.rules.plan import Plan
from tests.wave110a_kit import *

ARB = "Leonin Arbiter"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


def _lands(s):
    return [c for c in s.state.zones["p1:battlefield"] if s.state.cards[c].name == "Forest"]


def _blocked(s, who):
    return prohibitions.cant_search(Plan(s.state, "p1", s.cards, None), who, who) is not None


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(ARB)).level == "FULL"


def test_players_cannot_search_until_one_pays_two_and_then_only_that_player_and_only_this_turn(cards):
    s = build(cards, [ARB, "Rampant Growth"])
    arb = put(s, ARB)
    cast(s, "Rampant Growth")
    answer(s)
    assert not _lands(s) and _blocked(s, "p1") and _blocked(s, "p2")  # no card found: the search can't happen
    shown = s.view("p1")["rules"]["stats"][arb.id]
    assert shown["end_cost"] == "{2}" and shown["end_label"] == "Ignore Leonin Arbiter until end of turn"  # (the client's label: ignoring, not ending)
    fund(s, "{2}")
    act(s, "p1", type="end_effect", card_id=arb.id)  # special action: the cost is paid, no stack object
    assert not s.state.zones["stack"] and not _blocked(s, "p1") and _blocked(s, "p2")
    cast(s, "Rampant Growth")
    answer(s)
    assert len(_lands(s)) == 1
    check(s)
    next_turn(s)
    assert _blocked(s, "p1")  # until end of turn only

