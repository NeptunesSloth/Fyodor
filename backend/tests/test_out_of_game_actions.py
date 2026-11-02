"""-- out of the game -- a player who conceded or lost no longer takes part (800.4a; 104.3a: a player who concedes leaves the
game immediately), so the table refuses the actions that would move the game for them: the steps and turns, the stack,
cards, life and counters. They keep what a watcher at the table does: chat, the table's dice, their own name and look,
their rules preferences, stepping aside from a response check, and (the host) the host's table tools. The rules engine
already refused their rules intents ("You have left this game"); this covers the table tools around it.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import DeckCard, PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act, enable, find


def replay_matches(s: GameSession) -> None:
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")


def loaded(s: GameSession) -> GameSession:
    """Saved and loaded: the same table, in a new session (as after a restart)."""
    replay_matches(s)
    dumped = s.state.model_dump(mode="json")
    state = GameState.model_validate(dumped)
    assert state.model_dump(mode="json") == dumped
    return GameSession(state, cards=s.cards)


def three(cards, *, rules: bool = True) -> GameSession:
    cmd, land = cards.resolve("Krenko, Mob Boss"), cards.resolve("Mountain")
    setups = [PlayerSetup(n, cards=[DeckCard("commander", 1, cmd["name"], cmd["id"]), DeckCard("main", 9, land["name"], land["id"])])
              for n in ("Ann", "Ben", "Cat")]
    state = new_game(setups, shuffle=False, first_player=0)
    if rules:
        enable(state)
    return GameSession(state, cards=cards)


def moving(s: GameSession, pid: str) -> list[dict]:
    """Table tools that would move the game, as ``pid`` would send them."""
    mountain = find(s.state, "Mountain", pid).id
    krenko = find(s.state, "Krenko, Mob Boss", "p1").id
    return [
        {"type": "phase", "to": "next"},
        {"type": "phase", "to": "prev"},
        {"type": "next_turn"},
        {"type": "resolve_top"},
        {"type": "move", "card_ids": [mountain], "to": {"zone": "battlefield"}},
        {"type": "draw", "count": 1},
        {"type": "tap", "card_ids": [krenko]},
        {"type": "set_life", "player": "p1", "value": 1},
        {"type": "life", "player": pid, "delta": 5},
        {"type": "set_position", "moves": [[krenko, 10, 10]]},
    ]


def refused(s: GameSession, pid: str, payload: dict) -> str:
    seq, history = s.state.seq, len(s.history.actions)
    with pytest.raises(ActionError) as exc:
        act(s, pid, **payload)
    assert (s.state.seq, len(s.history.actions)) == (seq, history), payload  # nothing applied, nothing recorded
    return str(exc.value)


def test_a_player_who_conceded_can_no_longer_move_the_game_and_a_save_keeps_it_so(cards):
    s = three(cards)
    act(s, "p3", type="concede")
    assert s.state.rules.conceded == ["p3"]
    for payload in moving(s, "p3"):
        msg = refused(s, "p3", payload)
        assert msg == "You're out of this game (you conceded): you can watch and chat, but not move the game."
    # the rules engine refuses their rules intents, as before
    with pytest.raises(ActionError, match="You have left this game"):
        act(s, "p3", type="pass_priority")
    # what a watcher at the table does still works
    act(s, "p3", type="chat", text="gg, I'll watch")
    act(s, "p3", type="roll", sides=20)
    act(s, "p3", type="rename_player", name="Cat (out)")
    act(s, "p3", type="set_prefs", hold_priority=True)
    assert s.state.players["p3"].name == "Cat (out)"
    # the players still in the game play on, table tools included
    act(s, "p1", type="phase", to="next")
    replay_matches(s)

    again = loaded(s)
    assert refused(again, "p3", {"type": "next_turn"}).startswith("You're out of this game")
    act(again, "p2", type="set_life", player="p2", value=39)
    replay_matches(again)


def test_a_player_who_lost_is_refused_too_also_while_automation_is_paused(cards):
    s = three(cards)
    act(s, "p2", type="set_life", player="p2", value=0)
    act(s, s.state.rules.priority, type="pass_priority")  # the state-based check: Ben loses (704.5a)
    assert "p2" in s.state.rules.lost and s.state.rules.winner is None
    for payload in moving(s, "p2"):
        assert refused(s, "p2", payload) == "You're out of this game (you lost): you can watch and chat, but not move the game."
    act(s, "p1", type="configure", automation_paused=True)  # the host pauses: everyone plays by hand meanwhile...
    assert s.state.rules.paused
    assert refused(s, "p2", {"type": "phase", "to": "next"}).startswith("You're out of this game")  # ...except who is out
    act(s, "p3", type="phase", to="next")
    act(s, "p2", type="chat", text="still here")
    again = loaded(s)
    assert refused(again, "p2", {"type": "next_turn"}).startswith("You're out of this game")
    replay_matches(again)


def test_the_host_keeps_the_hosts_table_tools_after_going_out(cards):
    s = three(cards)
    act(s, "p1", type="concede")
    assert refused(s, "p1", {"type": "next_turn"}).startswith("You're out of this game")
    act(s, "p1", type="configure", automation_paused=True)  # host-only at a LAN table (the API checks who the host is)
    assert s.state.rules.paused
    act(s, "p1", type="remove_player", player="p3")
    assert s.state.players["p3"].left
    replay_matches(loaded(s))


def test_server_built_actions_and_tables_without_the_rules_engine_are_untouched(cards):
    s = three(cards, rules=False)
    assert s.state.rules is None
    act(s, "p3", type="phase", to="next")  # nobody can be out without the rules engine: the table tools work as before
    act(s, "p3", type="next_turn")
    replay_matches(s)


def test_what_an_out_player_may_still_send_is_a_short_list():
    from app.game.out_of_game import OUT_MAY

    # the table's chatter, their own seat's name and look, stepping aside from a response check, the host's table tools, and
    # rules intents (the engine decides those: preferences go through, everything else is refused)
    assert {"chat", "roll", "coin", "rename_player", "set_appearance", "end_view", "response_pass", "response_auto",
            "configure", "remove_player", "set_table_playmat", "restart_game"} <= OUT_MAY
    for kind in ("phase", "next_turn", "resolve_top", "move", "draw", "tap", "life", "set_life", "set_position", "counter",
                 "create_token", "attack", "block", "response_respond", "response_close", "delete_card", "note", "create_arrow"):
        assert kind not in OUT_MAY


def test_over_the_api_a_conceded_seat_gets_a_clear_refusal_and_can_still_chat(client):
    from tests.test_elimination_hub import P1_DECK, P2_DECK, P3_DECK, h

    decks = [client.post("/api/decks", json={"text": t}).json()["id"] for t in (P1_DECK, P2_DECK, P3_DECK)]
    game = client.post("/api/games", json={
        "mode": "lan", "automation": "full", "name": "Friday",
        "players": [{"name": n, "deck_id": d} for n, d in zip(("Alice", "Bob", "Carol"), decks, strict=True)],
    })
    assert game.status_code == 201, game.text
    gid, code = game.json()["game"]["id"], game.json()["game"]["code"]
    client.post("/api/join", json={"code": code})
    carol = client.post("/api/join", json={"code": code}).json()["token"]
    post = lambda action: client.post(f"/api/games/{gid}/actions", json={"action": action}, headers=h(carol))  # noqa: E731
    assert post({"type": "concede"}).status_code == 200
    for action in ({"type": "next_turn"}, {"type": "phase", "to": "next"}, {"type": "resolve_top"}):
        res = post(action)
        assert res.status_code == 409 and res.json()["detail"].startswith("You're out of this game (you conceded)"), res.text
    assert post({"type": "chat", "text": "watching now"}).status_code == 200
    with client.websocket_connect(f"/ws/games/{gid}?token={carol}") as ws:
        ws.receive_json()  # the view
        ws.send_json({"type": "action", "id": 1, "action": {"type": "next_turn"}})
        msg = ws.receive_json()
        while msg.get("type") not in ("error", "ack"):
            msg = ws.receive_json()
        assert msg["type"] == "error" and msg["message"].startswith("You're out of this game"), msg
