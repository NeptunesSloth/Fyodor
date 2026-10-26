"""Wave 110M: instants and sorceries whose last unread sentence is now read. Every scenario checks the replay and a save and a load.

* 614.1a, 614.5, 104.3b: "The next time you would lose the game this turn, instead draw seven cards and your life total becomes 1. Exile Stunning Reversal."
  (Stunning Reversal): a one-shot replacement for this turn; the second loss, or one on a later turn, is not replaced.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave110m_kit import *

REVERSAL = "Stunning Reversal"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([REVERSAL])


def reversal_table(cards):
    s = build(cards, [REVERSAL, "Lightning Bolt"], forests=20)
    act(s, "p1", type="set_life", player="p1", value=3)
    cast(s, REVERSAL)
    answer(s)
    return s


def test_stunning_reversal_replaces_the_next_loss_with_seven_cards_and_one_life(cards):
    s = reversal_table(cards)
    assert zone_of(s, REVERSAL) == "p1:exile" and life(s) == 3
    hand = len(s.state.zones["p1:hand"])
    cast(s, "Lightning Bolt", ["p1"])
    answer(s)
    assert s.state.rules.winner is None and life(s) == 1 and len(s.state.zones["p1:hand"]) == hand + 7
    check(s)


def test_stunning_reversal_replaces_only_the_next_loss_this_turn(cards):
    s = reversal_table(cards)
    cast(s, "Lightning Bolt", ["p1"])
    answer(s)
    assert life(s) == 1
    act(s, "p1", type="set_life", player="p1", value=0)
    act(s, "p1", type="pass_priority")  # (704.3: the state-based actions are checked before a player would receive priority)
    answer(s)
    assert s.state.rules.winner == "p2"
    check(s)


def test_stunning_reversal_ends_with_the_turn(cards):
    s = reversal_table(cards)
    to_phase(s, "main1", turn=s.state.turn.number + 2)
    act(s, "p1", type="set_life", player="p1", value=0)
    act(s, "p1", type="pass_priority")
    answer(s)
    assert s.state.rules.winner == "p2"
    check(s)


# -- Choice of Damnations ------------------------------------------------------------------------------------------------------------------
DAMN = "Choice of Damnations"
test_damnations_full = full_test([DAMN])


def type_number(s, n):
    """Pass priority until a typed-number decision is asked, and answer it."""
    until(s, lambda s: s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.options[0].group == "number"
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[], name=str(n))


def damnations_table(cards):
    s = build(cards, [DAMN], ["Grizzly Bears", "Llanowar Elves", "Elite Vanguard"], forests=20)
    for n in ("Grizzly Bears", "Llanowar Elves", "Elite Vanguard"):
        put(s, n, "p2")
    return s


def theirs(s):
    return sorted(s.state.cards[c].name for c in s.state.zones["p2:battlefield"])


@pytest.mark.parametrize("number,controller,life_after,kept", [
    (5, "yes", 35, 3),         # lose that much life
    (0, "yes", 40, 3),         # losing 0 life
    (1, "no", 40, 1),          # sacrifice all but one: they keep one of their choice
    (0, "no", 40, 0),          # all of them
    (3, "no", 40, 3),          # exactly as many as they have: none is sacrificed
    (9, "no", 40, 3),          # more than they have
])
def test_choice_of_damnations_lose_life_or_sacrifice_all_but_the_chosen_number(cards, number, controller, life_after, kept):
    s = damnations_table(cards)
    cast(s, DAMN, ["p2"])
    type_number(s, number)
    picks = [controller]
    if controller == "no" and 0 < number < 3:
        picks.append([card_named(s, "Llanowar Elves", "p2").id])
    answer(s, *picks)
    assert life(s, "p2") == life_after and len(theirs(s)) == kept
    if kept == 1:
        assert theirs(s) == ["Llanowar Elves"]  # (the permanent the player kept)
    check(s)
