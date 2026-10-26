"""Wave 110M: Nihiloor. 603.12a: "When you do" triggers once each time the tap is done, one for each opponent; 115.1 / 608.2h: the target's power is capped by the tapped
creature's as it last existed; 611.2b: "for as long as you control Nihiloor"; 508.1 / 603.2: an attack with a creature an opponent owns. Every scenario checks the replay and a save and a load.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave36a_kit import ready
from tests.wave110m_kit import *

NIHILOOR = "Nihiloor"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([NIHILOOR])


def cast_nihiloor(cards, theirs=("Elite Vanguard", "Hill Giant")):
    s = build(cards, [NIHILOOR, "Grizzly Bears", "Murder"], list(theirs), forests=20)
    bears = put(s, "Grizzly Bears")
    ready(s, "Grizzly Bears")
    for n in theirs:
        put(s, n, "p2")
    cast(s, NIHILOOR)
    return s, bears


def test_tapping_a_creature_steals_a_creature_of_no_greater_power(cards):
    s, bears = cast_nihiloor(cards)
    vanguard = card_named(s, "Elite Vanguard", "p2")
    giant = card_named(s, "Hill Giant", "p2")
    answer(s, bears.id)  # tap the Bears (power 2): the only legal target is the Vanguard, the Giant's power is 3
    assert s.state.cards[bears.id].tapped and s.state.cards[vanguard.id].controller == "p1" and s.state.cards[giant.id].controller == "p2"
    check(s)


def test_tapping_nothing_steals_nothing(cards):
    s, bears = cast_nihiloor(cards)
    d = s.state.rules.decision
    assert d is not None and d.min_choices == 0
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[])
    answer(s)
    assert not s.state.cards[bears.id].tapped and card_named(s, "Elite Vanguard", "p2").controller == "p2"
    check(s)


def test_the_steal_ends_when_nihiloor_leaves(cards):
    s, bears = cast_nihiloor(cards)
    vanguard = card_named(s, "Elite Vanguard", "p2")
    answer(s, bears.id)
    assert s.state.cards[vanguard.id].controller == "p1"
    cast(s, "Murder", [card_named(s, NIHILOOR).id])  # (Nihiloor dies by its own controller's spell)
    answer(s)
    assert s.state.cards[vanguard.id].controller == "p2"
    check(s)


def test_attacking_with_a_creature_an_opponent_owns_drains_its_owner(cards):
    s, bears = cast_nihiloor(cards)
    vanguard = card_named(s, "Elite Vanguard", "p2")
    answer(s, bears.id)
    stops(s)
    next_turn(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": vanguard.id, "target": "p2"}, {"card_id": bears.id, "target": "p2"}])
    answer(s)
    assert life(s) == 42 and life(s, "p2") == 38  # (only the creature p2 owns triggers it, not the Bears)
    check(s)


def test_each_opponent_gets_their_own_tap_and_steal(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    setups = [PlayerSetup("Alice", cards=deck(cards, "Krenko, Mob Boss", [(1, NIHILOOR), (1, "Grizzly Bears"), (1, "Hill Giant"), (9, "Forest")])),
              PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [(1, "Elite Vanguard"), (9, "Island")])),
              PlayerSetup("Carol", cards=deck(cards, "Krenko, Mob Boss", [(1, "Elite Vanguard"), (9, "Forest")]))]
    s = GameSession(enable(new_game(setups, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    bears, giant = put(s, "Grizzly Bears"), put(s, "Hill Giant")
    ready(s, "Grizzly Bears", "Hill Giant")
    bob, carol = put(s, "Elite Vanguard", "p2"), put(s, "Elite Vanguard", "p3")
    cast(s, NIHILOOR)
    answer(s, bears.id, giant.id)  # Bob's turn of the loop taps the Bears, then Carol's taps the Giant
    assert s.state.cards[bears.id].tapped and s.state.cards[giant.id].tapped
    assert s.state.cards[bob.id].controller == s.state.cards[carol.id].controller == "p1"
    check(s)
