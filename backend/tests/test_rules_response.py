"""RESPONSE OFF / AUTO / ON, stops, temporary overrides (force stop, pass until …, hold after this
resolves), bluff stops and remembered answers. Magic's priority rules stay authoritative: these
only decide when the engine passes *for* a player."""

from __future__ import annotations

import json

import pytest

from app.game.errors import ActionError
from app.game.session import GameSession
from tests.game_helpers import act, enable, find, make_session


@pytest.fixture()
def s(cards):
    return GameSession(enable(make_session(cards).state), cards=cards)


def rules(s):
    return s.state.rules


def where(s):
    return s.state.turn.number, s.state.turn.phase, rules(s).priority


def main1(s):
    act(s, "p1", type="pass_priority")
    assert where(s) == (1, "main1", "p1")


def test_response_on_stops_at_every_priority(s):
    act(s, "p2", type="set_prefs", response="on")
    act(s, "p1", type="pass_priority")  # Alice passes in her upkeep…
    assert where(s) == (1, "upkeep", "p2")  # …and Bob wants every priority (for bluffing)
    act(s, "p2", type="pass_priority")
    assert where(s) == (1, "draw", "p2")  # Alice (AUTO) has no stop in her draw step; Bob does


def test_response_off_runs_through_a_turn_with_nothing_to_do(s):
    act(s, "p1", type="set_prefs", response="off")
    act(s, "p1", type="pass_priority")  # nothing in hand: no stop even in main 1
    assert where(s) == (2, "main1", "p2")


def test_response_off_still_stops_when_there_is_something_to_do(s):
    act(s, "p1", type="draw", count=7)
    act(s, "p1", type="set_prefs", response="off")
    act(s, "p1", type="pass_priority")
    assert where(s) == (1, "main1", "p1")  # a land to play: a turn can't run past its owner


def test_force_stop_is_registered_any_time_and_consumed(s):
    main1(s)
    act(s, "p2", type="set_prefs", force_stop=True)  # Bob doesn't have priority: registered anyway
    act(s, "p1", type="pass_priority")
    assert where(s) == (1, "main1", "p2")  # Bob gets his stop
    act(s, "p2", type="pass_priority")
    assert where(s) == (1, "main2", "p1") and not rules(s).prefs["p2"].force_stop


def test_pass_until_next_turn(s):
    main1(s)
    act(s, "p1", type="pass_priority", until="next_turn")  # skips Alice's own main-2 stop…
    assert where(s) == (2, "upkeep", "p1")  # …and stops at the first priority of the next turn
    assert rules(s).prefs["p1"].pass_until is None  # met and cleared (Bob's turn is a new turn)


def test_pass_until_needs_a_stack_for_resolve_controls(s):
    main1(s)
    with pytest.raises(ActionError, match="stack is empty"):
        act(s, "p1", type="pass_priority", until="stack_empty")


def cast_ring(s):
    act(s, "p1", type="draw", count=7)
    act(s, "p1", type="play_land", card_id=find(s.state, "Mountain", "p1").id)
    ring = find(s.state, "Sol Ring", "p1")
    act(s, "p1", type="cast_spell", card_id=ring.id)
    return ring


def bob_has_counterspell(s, untapped=True):
    act(s, "p2", type="draw", count=7)
    for island in [c for c in s.state.cards.values() if c.name == "Island" and c.zone == "p2:hand"][:2]:
        act(s, "p2", type="move", card_ids=[island.id], to={"zone": "battlefield"})
        if not untapped:
            act(s, "p2", type="tap", card_ids=[island.id], tapped=True)


def test_auto_stops_only_with_a_real_response(s):
    main1(s)
    bob_has_counterspell(s)
    ring = cast_ring(s)
    assert where(s)[2] == "p2" and s.state.cards[ring.id].zone == "stack"  # Bob could Counterspell
    act(s, "p2", type="pass_priority")
    assert s.state.cards[ring.id].zone == "p1:battlefield"


def test_auto_passes_silently_and_bluff_stops_use_only_public_information(s, cards):
    main1(s)
    bob_has_counterspell(s, untapped=False)  # no mana: no real response
    ring = cast_ring(s)
    assert s.state.cards[ring.id].zone == "p1:battlefield" and where(s) == (1, "main1", "p1")
    log = json.dumps(s.view("p1")["log"])
    assert "no playable" not in log and "no response" not in log  # never tell the table why someone passed
    s2 = GameSession(enable(make_session(cards).state), cards=cards)
    main1(s2)
    act(s2, "p2", type="set_prefs", bluff_stops=True)
    act(s2, "p2", type="draw", count=7)
    island = next(c for c in s2.state.cards.values() if c.name == "Island" and c.zone == "p2:hand")
    act(s2, "p2", type="move", card_ids=[island.id], to={"zone": "battlefield"})
    ring = cast_ring(s2)
    assert where(s2)[2] == "p2" and s2.state.cards[ring.id].zone == "stack"  # cards in hand + untapped land


def test_hold_after_this_resolves_needs_a_stack_object(s):
    main1(s)
    ring = cast_ring(s)  # Bob has nothing: it resolves, Alice keeps her main phase
    with pytest.raises(ActionError, match="isn't on the stack"):
        act(s, "p2", type="set_prefs", stop_after=ring.id)


def test_stop_after_and_pass_until_stack_changes(s):
    main1(s)
    act(s, "p1", type="set_prefs", hold_priority=True)
    ring = cast_ring(s)
    assert where(s)[2] == "p1" and s.state.cards[ring.id].zone == "stack"  # held priority
    act(s, "p2", type="set_prefs", stop_after=ring.id)  # HOLD AFTER THIS RESOLVES (Bob, any time)
    act(s, "p1", type="pass_priority", until="stack_changes")  # RESOLVE ONE
    # Bob has no response: auto-passed; Sol Ring resolves; Alice's RESOLVE ONE is met…
    assert s.state.cards[ring.id].zone == "p1:battlefield" and where(s) == (1, "main1", "p1")
    act(s, "p1", type="pass_priority")
    assert where(s) == (1, "main1", "p2")  # …and Bob asked to stop once it had resolved
    assert rules(s).prefs["p2"].stop_after is None


def test_pass_until_next_action(s):
    main1(s)
    act(s, "p2", type="set_prefs", response="on")
    act(s, "p1", type="pass_priority")
    assert where(s) == (1, "main1", "p2")
    act(s, "p2", type="pass_priority", until="next_action")
    assert where(s) == (1, "main2", "p1")  # Bob's ON stops are skipped while he waits
    act(s, "p1", type="draw", count=7)
    act(s, "p1", type="play_land", card_id=find(s.state, "Mountain", "p1").id)  # Alice acts
    act(s, "p1", type="pass_priority")
    assert where(s) == (1, "main2", "p2") and rules(s).prefs["p2"].pass_until is None


def test_preferences_are_private(s):
    act(s, "p1", type="set_prefs", response="on", payment="manual")
    assert s.view("p1")["rules"]["prefs"]["payment"] == "manual"
    assert s.view("p2")["rules"]["prefs"]["payment"] == "auto"  # Bob sees his own, not Alice's
    assert s.view("p2")["rules"]["status"] == {"auto": "FULL", "resp": "AUTO"}
    assert s.view("p1")["rules"]["status"]["resp"] == "ON"


def test_remembered_answers_apply_in_the_same_context(s):
    main1(s)
    act(s, "p2", type="set_prefs", response="on")  # (so the turn doesn't run on between the checks)
    krenko = find(s.state, "Krenko, Mob Boss", "p1")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"})
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "graveyard"})
    act(s, "p1", type="pass_priority")
    d = rules(s).decision
    assert d.kind == "confirm" and s.view("p1")["rules"]["decision"]["rememberable"]
    assert "rememberable" not in s.view("p2")["rules"]["decision"]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"], remember="yes_this_turn")
    assert s.state.cards[krenko.id].zone == "p1:command"
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"})
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "graveyard"})
    act(s, rules(s).priority, type="pass_priority")
    assert rules(s).decision is None and s.state.cards[krenko.id].zone == "p1:command"  # remembered: no prompt
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"})
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "exile"})  # a different situation
    act(s, rules(s).priority, type="pass_priority")
    assert rules(s).decision.kind == "confirm"  # asked again
    act(s, "p1", type="set_prefs", cancel_all_yields=True)
    assert rules(s).prefs["p1"].yields == []
