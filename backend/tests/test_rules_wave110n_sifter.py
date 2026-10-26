"""Wave 110N: Timesifter (each player exiles the top card; the greatest mana value takes an extra turn, 500.7; ties repeat)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

SIFTER = "Timesifter"
EXTRA = [
    real(SIFTER, "{4}", 4, "Artifact Creature — Construct",
         "At the beginning of each upkeep, each player exiles the top card of their library. The player who exiled the card with the greatest mana value takes an extra turn after this one. "
         "If two or more players' cards are tied for greatest, the tied players repeat this process until the tie is broken.", ("2", "2")),
    real("One Mana", "{1}", 1, "Artifact", "", None),
    real("Three Mana", "{3}", 3, "Artifact", "", None),
    real("Four Mana", "{4}", 4, "Artifact", "", None),
    real("Two Mana", "{2}", 2, "Artifact", "", None),
]


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, EXTRA)


test_full = full_test([SIFTER])


def on_top(s, pid, *names):
    for n in reversed(names):
        act(s, pid, type="move", card_ids=[card_named(s, n, pid).id], to={"player": pid, "zone": "library"}, position="top")


def run(cards, mine, theirs):
    s = build(cards, [SIFTER, "One Mana", "Three Mana", "Four Mana", "Two Mana"], ["One Mana", "Three Mana", "Four Mana", "Two Mana"], forests=30, islands=30)
    put(s, SIFTER)
    on_top(s, "p1", *mine)
    on_top(s, "p2", *theirs)
    act(s, "p1", type="set_stops", own=STEPS + ["upkeep"], others=STEPS + ["upkeep"], smart_pass=False)
    # Alice's turn 1 is under way; the next upkeep is Bob's (turn 2), whose trigger starts the process
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "upkeep" and s.state.rules.priority == "p1")
    answer(s)
    # (it would go on triggering at every upkeep, and with lands on top of both libraries that goes on until they are empty: take it away)
    act(s, "p1", type="move", card_ids=[card_named(s, SIFTER).id], to={"player": "p1", "zone": "graveyard"})
    return s


def after_turn_two(s):
    """Who plays turns 3 and 4 (500.7: the extra turn comes right after turn 2, then the order goes on as if it had not been taken)."""
    act(s, "p1", type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    out = []
    for n in (3, 4):
        until(s, lambda s, n=n: s.state.turn.number == n and s.state.turn.phase == "main1")
        out.append(s.state.turn.active_player)
    return tuple(out)


def exiled(s, pid):
    return sorted(s.state.cards[c].name for c in s.state.zones.get(f"{pid}:exile", []))


@pytest.mark.parametrize(("mine", "theirs", "next_player"), [
    (["Three Mana"], ["One Mana"], ("p1", "p1")),   # Alice's card has the greater mana value: her extra turn 3, then turn 4 (hers too, after Bob's turn 2)
    (["One Mana"], ["Three Mana"], ("p2", "p1")),   # Bob's: the extra turn is his own, after turn 2
])
def test_the_greatest_mana_value_takes_the_extra_turn(cards, mine, theirs, next_player):
    s = run(cards, mine, theirs)
    assert exiled(s, "p1") == mine and exiled(s, "p2") == theirs
    assert after_turn_two(s) == next_player
    check(s)


def test_a_tie_sends_the_tied_players_round_again(cards):
    s = run(cards, ["Two Mana", "One Mana"], ["Two Mana", "Four Mana"])
    assert exiled(s, "p1") == ["One Mana", "Two Mana"] and exiled(s, "p2") == ["Four Mana", "Two Mana"]
    assert after_turn_two(s) == ("p2", "p1")
    check(s)


def test_with_nothing_left_to_break_the_tie_nobody_takes_an_extra_turn(cards):
    s = build(cards, [SIFTER, "One Mana"], ["One Mana"], forests=0, islands=0)
    put(s, SIFTER)
    for pid in ("p1", "p2"):  # a one-card library each
        for c in list(s.state.zones[f"{pid}:library"]):
            if s.state.cards[c].name != "One Mana":
                act(s, pid, type="move", card_ids=[c], to={"player": pid, "zone": "graveyard"})
    act(s, "p1", type="set_stops", own=STEPS + ["upkeep"], others=STEPS + ["upkeep"], smart_pass=False)
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "upkeep" and s.state.rules.priority == "p1")
    answer(s)
    assert exiled(s, "p1") == ["One Mana"] and exiled(s, "p2") == ["One Mana"]
    check(s)
