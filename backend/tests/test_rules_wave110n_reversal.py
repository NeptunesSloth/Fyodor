"""Wave 110N: Reversal of Fortune (707.12 a copy of a revealed card is cast free; 704.5e it ceases to exist if not cast)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

REVERSAL = "Reversal of Fortune"


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, [])


test_full = full_test([REVERSAL])


def start(cards):
    s = build(cards, [REVERSAL], ["Lightning Bolt", "Grizzly Bears"])
    for n in ("Lightning Bolt", "Grizzly Bears"):
        to_hand(s, n, "p2")
    cast(s, REVERSAL, ["p2"])
    return s


def dec(s):
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            return d
        act(s, s.state.rules.priority, type="pass_priority")


def copies(s):
    return [c for c in s.state.cards.values() if c.copy_of is not None and not c.zone.startswith("stack")]


def pick(s, *ids):
    d = dec(s)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(ids))


def test_the_copy_is_cast_for_free_and_the_original_stays_in_the_hand(cards):
    s = start(cards)
    d = dec(s)
    assert {o.label for o in d.options} == {"Lightning Bolt"}  # only the instant or sorcery card can be chosen
    pick(s, d.options[0].id)
    d = dec(s)
    pick(s, d.options[0].id)  # cast the copy
    d = dec(s)
    if d is not None and d.kind != "declare_attackers":
        pick(s, "p2")  # its target
    answer(s)
    assert life(s, "p2") == 37 and zone_of(s, "Lightning Bolt", "p2") == "p2:hand" and not copies(s)
    check(s)


def test_not_casting_the_copy_leaves_nothing(cards):
    s = start(cards)
    d = dec(s)
    pick(s, d.options[0].id)
    pick(s)  # cast nothing
    answer(s)
    assert life(s, "p2") == 40 and zone_of(s, "Lightning Bolt", "p2") == "p2:hand" and not copies(s)
    check(s)


def test_copying_nothing_is_allowed(cards):
    s = start(cards)
    pick(s)
    answer(s)
    assert life(s, "p2") == 40 and not copies(s)
    check(s)
