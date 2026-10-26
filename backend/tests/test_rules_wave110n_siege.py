"""Wave 110N: Invasion of Arcavios (903.11: no card comes into a Commander game from outside it, so the Siege searches the library and graveyard)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

SIEGE = "Invasion of Arcavios // Invocation of the Founders"


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, [])


test_full = full_test([SIEGE])


def start(cards, grave, library):
    s = build(cards, [SIEGE, *grave, *library])
    for n in grave:
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"player": "p1", "zone": "graveyard"})
    c = to_hand(s, SIEGE)
    fund(s, "{3}{U}{U}")
    act(s, "p1", type="cast_spell", card_id=c.id)
    return s


def step(s, *ids):
    """Pass priority until a decision opens, then answer it."""
    for _ in range(20):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(ids))


def test_a_card_from_the_library_is_found_and_the_library_shuffled(cards):
    s = start(cards, ["Murder"], ["Lightning Bolt"])
    step(s, "both")
    lib = list(s.state.zones["p1:library"])
    step(s, card_named(s, "Lightning Bolt").id)
    answer(s)
    assert zone_of(s, "Lightning Bolt") == "p1:hand" and zone_of(s, "Murder") == "p1:graveyard"
    assert list(s.state.zones["p1:library"]) != [c for c in lib if c != card_named(s, "Lightning Bolt").id]  # (shuffled, 701.24)
    check(s)


def test_a_card_from_the_graveyard_is_found_and_the_library_is_left_alone(cards):
    s = start(cards, ["Murder"], ["Lightning Bolt"])
    step(s, "both")
    step(s, card_named(s, "Murder").id)
    answer(s)
    assert zone_of(s, "Murder") == "p1:hand" and zone_of(s, "Lightning Bolt") == "p1:library"
    check(s)


def test_searching_only_the_graveyard_does_not_shuffle(cards):
    s = start(cards, ["Murder"], ["Lightning Bolt"])
    lib = list(s.state.zones["p1:library"])
    step(s, "graveyard")
    step(s, card_named(s, "Murder").id)
    answer(s)
    assert zone_of(s, "Murder") == "p1:hand" and list(s.state.zones["p1:library"]) == lib
    check(s)
