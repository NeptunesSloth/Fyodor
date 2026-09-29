"""Declarative macros and solo-testing tools."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.game.errors import ActionError
from app.game.macros import MacroDef
from tests.fixtures.cards import TREASURE
from tests.game_helpers import act, find, make_session, zone


@pytest.fixture()
def s(cards):
    session = make_session(cards)
    act(session, "p1", type="draw", count=10)
    return session


def play(s, name):
    c = find(s.state, name, "p1")
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": "battlefield"}, x=100, y=100)
    return s.state.cards[c.id]


def test_macro_runs_all_steps_as_one_undoable_action(s):
    sol = play(s, "Sol Ring")
    macro = {"name": "Smothering Tithe-ish", "steps": [
        {"op": "CREATE_TOKEN", "token_card_id": TREASURE["id"], "count": 2},
        {"op": "ADD_COUNTER", "target": "this", "kind": "charge", "amount": 3},
        {"op": "CHANGE_LIFE", "player": "each_opponent", "delta": -1},
        {"op": "ADD_MANA", "mana": {"C": 2}},
        {"op": "ROLL_DIE", "sides": 6},
        {"op": "CREATE_MARKER", "name": "Hexproof"},
        {"op": "SET_CHOICE", "key": "Chosen type", "value": "Dragon"},
        {"op": "DISPLAY_TEXT", "text": "Whee"},
    ]}
    seq = s.state.seq
    act(s, "p1", type="run_macro", macro=macro, card_id=sol.id)
    sol = s.state.cards[sol.id]
    treasures = [c for c in s.state.cards.values() if c.name == "Treasure"]
    assert len(treasures) == 2 and treasures[0].token_source.name == "Sol Ring"
    assert sol.counters == {"charge": 3} and sol.effects[0].name == "Hexproof" and sol.choices == {"Chosen type": "Dragon"}
    assert s.state.players["p2"].life == 39 and s.state.players["p1"].mana == {"C": 2}
    assert s.state.seq == seq + 1  # one history entry
    log = json.dumps(s.view("p2")["log"], ensure_ascii=False)
    assert "ran “Smothering Tithe-ish”" in log and "Whee" in log
    s.undo("p1")
    assert not any(c.name == "Treasure" for c in s.state.cards.values()) and s.state.players["p2"].life == 40
    s.redo("p1")
    assert s.state.players["p2"].life == 39  # the die result was recorded, not re-rolled


def test_macros_are_data_only(s):
    for bad in (
        {"name": "x", "steps": [{"op": "EXEC", "code": "import os"}]},
        {"name": "x", "steps": []},
        {"name": "x", "steps": [{"op": "CHANGE_LIFE", "delta": 1, "eval": "1+1"}]},
        {"name": "x", "steps": [{"op": "ROLL_DIE", "sides": 1}]},
        {"name": "x", "steps": [{"op": "DISPLAY_TEXT", "text": "a"}] * 21},
    ):
        with pytest.raises(ValidationError):
            MacroDef.model_validate(bad)
    with pytest.raises(ActionError, match="needs a card"):
        act(s, "p1", type="run_macro", macro={"name": "n", "steps": [{"op": "ADD_COUNTER"}]})
    with pytest.raises(ActionError, match="Select"):
        act(s, "p1", type="run_macro", macro={"name": "n", "steps": [{"op": "MOVE_CARD", "target": "selected", "to": "hand"}]})
    forged = {"name": "n", "steps": [{"op": "DISPLAY_TEXT", "text": "hi"}]}
    act(s, "p1", type="run_macro", macro=forged, r=[{"type": "set_life", "player": "p2", "value": 0}])  # client r ignored
    assert s.state.players["p2"].life == 40


def test_macro_library_api(client):
    body = {"scope": "card", "oracle_id": "abc", "definition": {"name": "Untap all lands", "steps": [{"op": "DISPLAY_TEXT", "text": "untap"}]}}
    made = client.post("/api/macros", json=body).json()
    assert made["definition"]["version"] == 1 and made["scope"] == "card"
    lib = client.post("/api/macros", json={"scope": "library", "definition": {"name": "Coin", "steps": [{"op": "FLIP_COIN"}]}}).json()
    assert {m["name"] for m in client.get("/api/macros?oracle_id=abc").json()} == {"Untap all lands", "Coin"}
    assert {m["name"] for m in client.get("/api/macros?oracle_id=zzz").json()} == {"Coin"}
    assert client.post("/api/macros", json={"scope": "card", "definition": body["definition"]}).status_code == 422
    assert client.post("/api/macros", json={"definition": {"name": "x", "steps": [{"op": "SHELL"}]}}).status_code == 422
    from fastapi.testclient import TestClient
    remote = TestClient(client.app, client=("192.168.1.20", 50000))
    assert remote.delete(f"/api/macros/{lib['id']}").status_code == 403
    assert client.delete(f"/api/macros/{lib['id']}").status_code == 204


def test_spawn_test_objects_and_reset_deck(s, cards):
    with pytest.raises(ActionError, match="off at this table"):
        act(s, "p1", type="spawn_card", card_id=cards.resolve("Counterspell")["id"])
    act(s, "p1", type="configure", allow_test_objects=True)
    act(s, "p1", type="spawn_card", card_id=cards.resolve("Counterspell")["id"])
    spawned = next(c for c in s.state.cards.values() if c.test_object)
    assert spawned.name == "Counterspell" and spawned.zone == "p1:battlefield"
    assert s.view("p2")["cards"][spawned.id]["test_object"] is True
    library_before = len(zone(s.state, "p1", "library")) + len(zone(s.state, "p1", "hand"))
    sol = play(s, "Sol Ring")
    act(s, "p1", type="create_token", token={"card_id": TREASURE["id"]}, count=2)
    act(s, "p1", type="copy_card", card_id=sol.id)
    krenko = find(s.state, "Krenko, Mob Boss")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"})
    act(s, "p1", type="life", player="p1", delta=-12)
    act(s, "p1", type="reset_deck", draw=7)
    st = s.state
    assert not any(c.test_object or c.is_token or c.copy_of for c in st.cards.values() if c.owner == "p1")
    assert st.cards[krenko.id].zone == "p1:command"
    assert len(zone(st, "p1", "hand")) == 7 and len(zone(st, "p1", "library")) + 7 == library_before
    assert zone(st, "p1", "sideboard") and st.players["p1"].life == 40
    assert zone(st, "p1", "battlefield") == []
    s.undo("p1")  # undoable like anything else
    assert any(c.test_object for c in s.state.cards.values())


def test_restart_game(s):
    act(s, "p1", type="next_turn")
    act(s, "p2", type="draw", count=3)
    act(s, "p1", type="restart_game", draw=7)
    st = s.state
    assert st.turn.number == 1 and all(len(zone(st, p, "hand")) == 7 for p in ("p1", "p2"))
