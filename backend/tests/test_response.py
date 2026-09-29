"""The Response helper: ask before resolving / moving on, never lock the table."""

from __future__ import annotations

import json

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameSettings
from tests.game_helpers import act, deck, find


@pytest.fixture()
def s(cards):
    decks = [deck(cards, "Krenko, Mob Boss", [(1, "Lightning Bolt"), (1, "Sol Ring"), (10, "Mountain")]),
             deck(cards, "Atraxa, Praetors' Voice", [(1, "Counterspell"), (10, "Island")]),
             deck(cards, "Krenko, Mob Boss", [(11, "Mountain")])]
    state = new_game([PlayerSetup(n, cards=d) for n, d in zip(["Alice", "Bob", "Cara"], decks, strict=True)],
                     settings=GameSettings(priority_helper="simple"))
    session = GameSession(state, cards=cards)
    for p in ("p1", "p2", "p3"):
        act(session, p, type="draw", count=7)
    return session


def cast(s, pid, name):
    c = find(s.state, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "stack"})
    return c


def test_casting_asks_the_others_and_everyone_passing_closes_it(s):
    cast(s, "p1", "Lightning Bolt")
    w = s.state.response
    assert w.kind == "stack" and w.opener == "p1" and w.waiting == ["p2", "p3"] and "Lightning Bolt" in w.text
    with pytest.raises(ActionError, match="Nothing to pass"):
        act(s, "p1", type="response_pass")
    act(s, "p2", type="response_pass")
    act(s, "p3", type="response_pass")
    assert s.state.response is None
    # everyone just passed: resolving now doesn't ask again
    act(s, "p1", type="resolve_top")
    assert s.state.zones["stack"] == []


def test_resolve_and_next_step_wait_for_passes_then_happen(s):
    cast(s, "p1", "Lightning Bolt")
    act(s, "p2", type="response_pass")
    act(s, "p1", type="phase", to="next")  # a new request while Cara hasn't passed: a new check
    w = s.state.response
    assert w.kind == "phase" and w.waiting == ["p2", "p3"] and s.state.turn.phase == "untap"
    act(s, "p2", type="response_pass")
    act(s, "p3", type="response_pass")
    assert s.state.response is None and s.state.turn.phase == "upkeep"  # applied when the last one passed
    assert "wants to move to upkeep" in json.dumps(s.view("p2")["log"])


def test_respond_puts_the_request_on_hold(s):
    act(s, "p1", type="next_turn")
    assert s.state.response.kind == "turn"
    act(s, "p2", type="response_respond")
    assert s.state.response.responder == "p2" and s.state.turn.active_player == "p1"
    cast(s, "p2", "Counterspell")  # Bob's response replaces the check with his own
    assert s.state.response.opener == "p2" and s.state.response.waiting == ["p1", "p3"]


def test_proceed_anyway_force_and_auto_pass(s):
    act(s, "p1", type="phase", to="next", force=True)  # proceed anyway: no check at all
    assert s.state.response is None and s.state.turn.phase == "upkeep"
    act(s, "p3", type="response_auto")
    act(s, "p1", type="phase", to="next")
    assert s.state.response.waiting == ["p2"]
    act(s, "p1", type="response_close")  # the opener goes ahead
    assert s.state.response is None and s.state.turn.phase == "draw"
    # the host can force a check shut; others can't close someone else's check
    cast(s, "p1", "Sol Ring")
    with pytest.raises(ActionError, match="Only the player who asked"):
        act(s, "p2", type="response_close")
    act(s, "p2", type="response_close", as_host=True)
    assert s.state.response is None
    # auto-pass lasts until the end of the turn
    act(s, "p1", type="next_turn", force=True)
    assert s.state.auto_pass.get("p3") != s.state.turn.number


def test_clients_cannot_open_checks_with_arbitrary_intents(s):
    with pytest.raises(ActionError, match="opened by the server"):
        act(s, "p2", type="response_open", kind="turn", text="x", intent={"type": "set_life", "player": "p1", "life": 0})


def test_undo_restores_the_check(s):
    act(s, "p1", type="phase", to="next")
    act(s, "p2", type="response_pass")
    act(s, "p3", type="response_pass")
    assert s.state.turn.phase == "upkeep"
    s.undo("p3")
    assert s.state.turn.phase == "untap" and s.state.response.waiting == ["p3"]
    s.redo("p3")
    assert s.state.turn.phase == "upkeep"


def test_helper_off_changes_nothing(cards):
    state = new_game([PlayerSetup("A"), PlayerSetup("B")])
    session = GameSession(state, cards=cards)
    act(session, "p1", type="phase", to="next")
    assert session.state.response is None and session.state.turn.phase == "upkeep"


def test_host_only_force_over_the_api(client):
    body = client.post("/api/games", json={"mode": "lan", "players": [{"name": "A"}, {"name": "B"}]}).json()
    gid, alice = body["game"]["id"], body["seat"]["token"]
    bob = client.post("/api/join", json={"code": body["game"]["code"], "name": "B"}).json()["token"]

    def post(token, action):
        return client.post(f"/api/games/{gid}/actions", json={"action": action}, headers={"X-Seat-Token": token})

    assert post(alice, {"type": "phase", "to": "next"}).json()["response"]["kind"] == "phase"
    assert post(bob, {"type": "response_close", "as_host": True}).status_code == 403
    view = post(alice, {"type": "response_close", "as_host": True}).json()
    assert view["response"] is None and view["turn"]["phase"] == "upkeep"


def test_each_request_asks_again_after_an_applied_one(s):
    act(s, "p1", type="phase", to="next")
    act(s, "p2", type="response_pass")
    act(s, "p3", type="response_pass")
    act(s, "p1", type="phase", to="next")
    assert s.state.response is not None and s.state.turn.phase == "upkeep"
