"""Wave 110M: Aeon Engine. "Reverse the game's turn order." The players keep their seats; the order of turns, of priority and of every "in turn order" instruction
(APNAP, 101.4; 117.3d; 500.7) now runs the other way. Reversing twice restores it. Every scenario checks the replay and a save and a load.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.game_helpers import deck, enable
from tests.wave110m_kit import *

ENGINE = "Aeon Engine"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([ENGINE])


def three(cards):
    setups = [PlayerSetup("Alice", cards=deck(cards, "Krenko, Mob Boss", [(2, ENGINE), (9, "Forest")])),
              PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [(9, "Island")])),
              PlayerSetup("Carol", cards=deck(cards, "Krenko, Mob Boss", [(9, "Forest")]))]
    s = GameSession(enable(new_game(setups, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def reverse(s):
    engine = next(c for c in s.state.cards.values() if c.name == ENGINE and c.zone == "p1:battlefield")
    s.state.rules.controlled_since[engine.id].turn = 0
    act(s, "p1", type="activate_ability", card_id=engine.id, ability=1)
    answer(s)


def test_the_next_turn_goes_to_the_previous_seat_after_the_reversal(cards):
    s = three(cards)
    engine = put(s, ENGINE)
    reverse(s)
    assert s.state.cards[engine.id].zone == "p1:exile" and s.state.rules.turn_reversed110m
    assert s.state.turn_order() == ["p3", "p2", "p1"]
    stops(s)
    to_phase(s, "main1", turn=2)
    assert s.state.turn.active_player == "p3"
    to_phase(s, "main1", turn=3)
    assert s.state.turn.active_player == "p2"
    check(s)


def test_apnap_follows_the_new_direction(cards):
    from app.rules.plan import Plan

    s = three(cards)
    put(s, ENGINE)
    before = Plan(s.state, "p1", s.cards, None).apnap()
    reverse(s)
    after = Plan(s.state, "p1", s.cards, None).apnap()
    assert before == ["p1", "p2", "p3"] and after == ["p1", "p3", "p2"]
    check(s)


def test_a_second_reversal_restores_the_order(cards):
    s = three(cards)
    first = put(s, ENGINE)
    second = next(c for c in s.state.cards.values() if c.name == ENGINE and c.id != first.id)
    act(s, "p1", type="move", card_ids=[second.id], to={"player": "p1", "zone": "battlefield"})
    reverse(s)
    assert s.state.turn_order() == ["p3", "p2", "p1"]
    reverse(s)
    assert s.state.turn_order() == ["p1", "p2", "p3"] and not s.state.rules.turn_reversed110m
    check(s)
