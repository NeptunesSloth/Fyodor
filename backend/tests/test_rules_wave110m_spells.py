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


# -- Kaervek's Spite -----------------------------------------------------------------------------------------------------------------------
SPITE = "Kaervek's Spite"
test_spite_full = full_test([SPITE])


@pytest.mark.parametrize("hand_cards", [("Grizzly Bears", "Llanowar Elves"), ()])
def test_kaervek_spite_sacrifices_every_permanent_and_discards_the_hand_as_a_cost(cards, hand_cards):
    """601.2b, 118.3: both parts of the additional cost are paid as it is cast (the spell is already on the stack, so it isn't in the hand it discards)."""
    s = build(cards, [SPITE, "Grizzly Bears", "Llanowar Elves", "Elite Vanguard"], forests=20)
    board = [put(s, "Elite Vanguard"), put(s, "Forest")]
    hand = [to_hand(s, n) for n in hand_cards]
    cast(s, SPITE, ["p2"])
    assert all(zone_of(s, "Elite Vanguard") == "p1:graveyard" for _ in board[:1]) and board[1].id not in s.state.zones["p1:battlefield"]
    assert all(c.id in s.state.zones["p1:graveyard"] for c in hand) and not s.state.zones["p1:hand"]
    answer(s)
    assert life(s, "p2") == 35 and zone_of(s, SPITE) == "p1:graveyard"
    check(s)


# -- Rhino's Rampage -------------------------------------------------------------------------------------------------------------------------
RAMPAGE = "Rhino's Rampage"
test_rampage_full = full_test([RAMPAGE])


def rampage_table(cards, victim):
    s = build(cards, [RAMPAGE, "Grizzly Bears"], [victim, "Sol Ring", "Gilded Lotus", "Ornithopter"], forests=20)
    bears = put(s, "Grizzly Bears")
    for n in (victim, "Sol Ring", "Gilded Lotus", "Ornithopter"):
        put(s, n, "p2")
    return s, bears


@pytest.mark.parametrize("victim,excess", [("Llanowar Elves", True), ("Hill Giant", False)])
def test_rhino_rampage_destroys_an_artifact_only_when_excess_damage_was_dealt(cards, victim, excess):
    """Bears get +1/+0 (3 power): a 1/1 takes 2 excess damage, a 3/3 exactly lethal damage (120.10). The artifact is chosen as the reflexive ability goes on the stack."""
    s, bears = rampage_table(cards, victim)
    c = to_hand(s, RAMPAGE)
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[bears.id, card_named(s, victim, "p2").id], target_counts=[1, 1])
    if excess:
        d = None
        for _ in range(20):
            d = s.state.rules.decision
            if d is not None:
                break
            act(s, s.state.rules.priority, type="pass_priority")
        assert d is not None and {o.label for o in d.options} >= {"Sol Ring"} and not {o.label for o in d.options} & {"Gilded Lotus", "Ornithopter"}
        sol = card_named(s, "Sol Ring", "p2")
        answer(s, [sol.id])
        assert zone_of(s, "Sol Ring", "p2") == "p2:graveyard"
    else:
        answer(s)
        assert zone_of(s, "Sol Ring", "p2") == "p2:battlefield"
    assert zone_of(s, victim, "p2") == "p2:graveyard"
    assert zone_of(s, "Gilded Lotus", "p2") == "p2:battlefield" and zone_of(s, "Ornithopter", "p2") == "p2:battlefield"
    check(s)
