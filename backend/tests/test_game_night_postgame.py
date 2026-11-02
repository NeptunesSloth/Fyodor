"""Game night after the result and before the next start (docs/GAME_NIGHT_FLOW.md §2, docs/3D_DIRECTION.md §7a).

-- final board -- once a result is recorded the finished table can be looked at, never changed: every action (but table talk),
undo, redo, restore and mid-game deck load is refused, each viewer keeps seeing exactly what the game showed them, and the
rematch vote still works. -- seating -- the host arranges the lobby's seats; the turn-order setting decides who goes first
(the pod rule, unchanged and still the app's choice; a random player; or seat 1), and each game's d20 rolls are recorded.
"""

from __future__ import annotations

import pytest

from app.game.state import GameState
from app.multiplayer.lobby import LobbySettings
from app.multiplayer.night import FINAL_BOARD, Night, winner_last
from tests.test_game_night import _finish, seat_of, view
from tests.test_lobby import ALICE_DECK, BOB_DECK, create_lobby, h, lobby_of


@pytest.fixture()
def table(client):
    """A two-player LAN game started from the lobby under the pod rule (as in test_game_night)."""
    gid, code, alice = create_lobby(client, turn_order="pod")
    bob = client.post("/api/join", json={"code": code, "name": "Bob"}).json()["token"]
    for tok, deck in ((alice, ALICE_DECK), (bob, BOB_DECK)):
        assert client.post(f"/api/games/{gid}/lobby/deck", json={"text": deck}, headers=h(tok)).status_code == 200
        client.post(f"/api/games/{gid}/lobby/ready", json={"ready": True}, headers=h(tok))
    assert client.post(f"/api/games/{gid}/lobby/start", json={}, headers=h(alice)).status_code == 200
    return client, gid, alice, bob


def replay_matches(session) -> None:
    assert session.history.rebuild().model_dump(mode="json") == session.state.model_dump(mode="json")


def roundtrip(session) -> None:
    replay_matches(session)
    dumped = session.state.model_dump(mode="json")
    assert GameState.model_validate(dumped).model_dump(mode="json") == dumped


def board(state: GameState) -> dict:
    """Everything on the table (not the log, not the action counter)."""
    dumped = state.model_dump(mode="json")
    return {k: dumped[k] for k in ("players", "seat_order", "cards", "zones", "turn", "table", "arrows", "pregame", "settings")}


def ws_until(ws, pred):
    while True:
        msg = ws.receive_json()
        if pred(msg):
            return msg


# --------------------------------------------------------------------------- final board


def test_the_final_board_refuses_every_change_and_the_vote_still_works(table):
    client, gid, alice, bob = table
    hub = client.app.state.services.hub
    a, b = seat_of(client, gid, alice), seat_of(client, gid, bob)
    act = f"/api/games/{gid}/actions"
    snap = client.post(f"/api/games/{gid}/snapshots", json={"name": "mid"}, headers=h(alice)).json()
    assert client.post(act, json={"action": {"type": "set_life", "player": a, "value": 33}}, headers=h(alice)).status_code == 200
    _finish(client, gid, alice, bob, alice)
    room = hub.get(gid)
    before, cursor = board(room.session.state), room.session.history.cursor
    refused = [
        client.post(act, json={"action": {"type": "set_life", "player": a, "value": 1}}, headers=h(alice)),
        client.post(act, json={"action": {"type": "draw", "player": b, "count": 1}}, headers=h(bob)),
        client.post(act, json={"action": {"type": "restart_game"}}, headers=h(alice)),
        client.post(f"/api/games/{gid}/undo", json={}, headers=h(alice)),
        client.post(f"/api/games/{gid}/redo", json={}, headers=h(bob)),
        client.post(f"/api/games/{gid}/snapshots/{snap['id']}/restore", headers=h(alice)),
        client.post(f"/api/games/{gid}/history/1/restore", headers=h(alice)),
        client.post(f"/api/games/{gid}/load-deck", json={"text": BOB_DECK}, headers=h(bob)),
    ]
    for res in refused:
        assert res.status_code == 409 and res.json()["detail"] == FINAL_BOARD, res.text
    with client.websocket_connect(f"/ws/games/{gid}?token={bob}") as ws:
        ws.receive_json()
        ws.send_json({"type": "action", "id": 7, "action": {"type": "tap", "card_ids": []}, "client_action_id": "final-board-1"})
        assert ws_until(ws, lambda m: m.get("id") == 7) == {"type": "error", "id": 7, "status": "REJECTED", "message": FINAL_BOARD}
        ws.send_json({"type": "undo", "id": 8})
        assert ws_until(ws, lambda m: m.get("id") == 8)["message"] == FINAL_BOARD
    assert board(room.session.state) == before and room.session.history.cursor == cursor
    # nothing to undo or redo on the finished table; the players can still talk
    seen = view(client, gid, alice)["game"]
    assert seen["can_undo"] is False and seen["can_redo"] is False
    assert client.post(act, json={"action": {"type": "chat", "text": "gg"}}, headers=h(bob)).status_code == 200
    assert board(room.session.state) == before and "gg" in str(view(client, gid, alice)["log"])
    roundtrip(room.session)
    # the vote works from the final board: everyone rematches, and the new game takes actions again
    client.post(f"/api/games/{gid}/night/vote", json={"choice": "rematch"}, headers=h(alice))
    assert client.post(f"/api/games/{gid}/night/vote", json={"choice": "rematch"}, headers=h(bob)).json()["decision"] == "rematch"
    a = seat_of(client, gid, alice)
    assert client.post(act, json={"action": {"type": "set_life", "player": a, "value": 12}}, headers=h(alice)).status_code == 200
    assert view(client, gid, alice)["game"]["can_undo"] is True
    roundtrip(hub.get(gid).session)


def test_the_final_board_shows_each_viewer_exactly_what_the_game_did(table):
    client, gid, alice, bob = table
    code = client.get(f"/api/games/{gid}").json()["code"]
    spectator = client.post("/api/join", json={"code": code, "spectate": True}).json()["token"]
    tokens = {"alice": alice, "bob": bob, "spectator": spectator}

    def table_part(v: dict) -> dict:
        return {k: x for k, x in v.items() if k not in ("game", "log")}

    before = {who: table_part(view(client, gid, tok)) for who, tok in tokens.items()}
    with client.websocket_connect(f"/ws/games/{gid}?token={bob}") as ws:
        ws.receive_json()
        _finish(client, gid, alice, bob, bob)
        pushed = ws_until(ws, lambda m: m.get("type") == "state" and (m["view"]["game"]["night"] or {}).get("result"))["view"]
    after = {who: table_part(view(client, gid, tok)) for who, tok in tokens.items()}
    assert after == before  # hands, libraries, face-down cards: nothing more (or less) than during the game
    assert table_part(pushed) == after["bob"]
    for who, v in after.items():
        me = v["viewer"]
        for key, zone in v["zones"].items():
            if key.endswith(":hand") and not key.startswith(f"{me}:"):
                assert zone and all(i.startswith("hidden:") for i in zone), (who, key)
            if key.endswith(":library"):
                assert not zone["known"], (who, key)
    # the log after the result says who won, nothing hidden
    log = str(view(client, gid, spectator)["log"])
    for key, zone in client.app.state.services.hub.get(gid).session.state.zones.items():
        if key.endswith((":hand", ":library")):
            assert not any(cid in log for cid in zone)


def test_a_restarted_host_keeps_the_final_board(table):
    client, gid, alice, bob = table
    _finish(client, gid, alice, bob, alice)
    hub = client.app.state.services.hub
    room = hub.get(gid)
    meta, session = hub.meta(room), room.session
    hub.close(gid)
    hub.restore(meta, session, {})
    res = client.post(f"/api/games/{gid}/actions", json={"action": {"type": "draw", "player": "p1", "count": 1}}, headers=h(alice))
    assert res.status_code == 409 and res.json()["detail"] == FINAL_BOARD


def test_deleting_the_result_on_the_host_reopens_the_table(table):
    client, gid, alice, bob = table
    _finish(client, gid, alice, bob, alice)
    act = f"/api/games/{gid}/actions"
    draw = {"action": {"type": "draw", "player": seat_of(client, gid, bob), "count": 1}}
    assert client.post(act, json=draw, headers=h(bob)).status_code == 409
    rid = client.get(f"/api/games/{gid}/result").json()["id"]
    assert client.delete(f"/api/pod/results/{rid}").status_code == 204
    night = view(client, gid, bob)["game"]["night"]
    assert night["result"] is None and night["history"] == [] and night["votes"] == {}
    assert client.post(act, json=draw, headers=h(bob)).status_code == 200  # the game goes on until a result is recorded again
    _finish(client, gid, alice, bob, bob)
    assert view(client, gid, bob)["game"]["night"]["history"][0]["winner_names"] == ["Bob"]


def test_old_records_and_settings_still_load():
    old = {"number": 2, "order_source": "winner_last", "rolls": [], "previous_winner": "p2", "result": None, "votes": {},
           "history": [{"number": 1, "result_type": "single", "winner_names": ["Alice"], "agreed": True, "order": ["Alice", "Bob"],
                        "turns": 3}], "last_winner_key": "tok"}
    night = Night.from_meta(old)
    assert night.public(str)["history"] == old["history"] and night.final_board() is None
    night.result = {"result_type": "draw", "winners": []}
    assert night.final_board("tap") == FINAL_BOARD and night.final_board("search_end") == FINAL_BOARD
    assert night.final_board("chat") is None and night.final_board("end_view") is None
    assert Night.from_meta(night.meta()).final_board() == FINAL_BOARD  # a restart keeps it
    # a lobby saved before "seats" existed keeps its turn order, and the API default stays "random"
    assert LobbySettings().turn_order == "random"
    assert LobbySettings.model_validate({"name": "Old", "seats": 4}).turn_order == "random"
    assert LobbySettings.model_validate({"turn_order": "pod"}).turn_order == "pod"


# --------------------------------------------------------------------------- seating


def _pod(client, **extra):
    gid, code, alice = create_lobby(client, **extra)
    bob = client.post("/api/join", json={"code": code, "name": "Bob"}).json()["token"]
    carol = client.post("/api/join", json={"code": code, "name": "Carol"}).json()["token"]
    for tok, deck in ((alice, ALICE_DECK), (bob, BOB_DECK), (carol, ALICE_DECK)):
        assert client.post(f"/api/games/{gid}/lobby/deck", json={"text": deck}, headers=h(tok)).status_code == 200
        client.post(f"/api/games/{gid}/lobby/ready", json={"ready": True}, headers=h(tok))
    return gid, alice, bob, carol


def _names(lobby: dict) -> dict[str, str]:
    return {s["id"]: s["name"] for s in lobby["seats"] if s["claimed"]}


def _arrangement(lobby: dict, names: list[str]) -> list[str]:
    """Every seat id, the named players' seats first in that order, then the open seats."""
    by_name = {v: k for k, v in _names(lobby).items()}
    first = [by_name[n] for n in names]
    return first + [s["id"] for s in lobby["seats"] if s["id"] not in first]


def test_the_host_arranges_the_seats_and_the_seat_order_starts_from_seat_one(client):
    gid, alice, bob, carol = _pod(client)
    arrange = f"/api/games/{gid}/lobby/arrange"
    lobby = lobby_of(client, gid, alice)
    order = _arrangement(lobby, ["Carol", "Alice", "Bob"])
    assert client.post(arrange, json={"order": order}, headers=h(bob)).status_code == 403  # the host's call
    assert client.post(arrange, json={"order": order[:2]}, headers=h(alice)).status_code == 422
    assert client.post(arrange, json={"order": [order[0]] * 4}, headers=h(alice)).status_code == 422
    with client.websocket_connect(f"/ws/games/{gid}?token={bob}") as ws:
        ws.receive_json()
        res = client.post(arrange, json={"order": order}, headers=h(alice))
        assert res.status_code == 200, res.text
        # Bob's open socket follows him to his new seat
        pushed = ws_until(ws, lambda m: m.get("type") == "lobby" and m["lobby"]["seats"][0]["name"] == "Carol")["lobby"]
        assert pushed["viewer"] == "p3"
    lobby = res.json()
    assert _names(lobby) == {"p1": "Carol", "p2": "Alice", "p3": "Bob"}
    seats = {s["name"]: s for s in lobby["seats"] if s["claimed"]}
    assert all(s["ready"] and s["deck"] for s in seats.values())  # decks and readiness stay with each player
    assert seats["Alice"]["host"] and lobby["is_host"] and lobby_of(client, gid, carol)["viewer"] == "p1"
    # the API's default turn order is unchanged: a random first player, the seats as arranged
    assert lobby["settings"]["turn_order"] == "random"
    assert lobby["turn_preview"] == {"source": "random", "order": ["p1", "p2", "p3"], "previous_winner": None}
    res = client.post(f"/api/games/{gid}/lobby/settings", json={"turn_order": "seats"}, headers=h(alice))
    assert res.status_code == 200 and res.json()["turn_preview"]["source"] == "seats"
    assert client.post(f"/api/games/{gid}/lobby/start", json={}, headers=h(alice)).status_code == 200
    state = client.app.state.services.hub.get(gid).session.state
    assert [state.players[p].name for p in state.seat_order] == ["Carol", "Alice", "Bob"]
    assert state.turn.active_player == "p1"
    night = view(client, gid, alice)["game"]["night"]
    assert night["order_source"] == "host" and night["rolls"] == []
    assert client.post(arrange, json={"order": order}, headers=h(alice)).status_code == 409  # not once the game is on


def test_the_pod_rule_rolls_records_the_rolls_and_follows_the_hosts_seating_after_a_win(client):
    gid, alice, bob, carol = _pod(client, turn_order="pod")
    assert client.post(f"/api/games/{gid}/lobby/start", json={}, headers=h(alice)).status_code == 200
    hub = client.app.state.services.hub
    state = hub.get(gid).session.state
    night = view(client, gid, alice)["game"]["night"]
    assert night["order_source"] == "d20" and night["rolls"]  # unchanged: the d20 sets game 1
    rolls = [{state.players[p].name: v for p, v in r.items()} for r in night["rolls"]]
    game1 = [state.players[p].name for p in state.seat_order]
    b = seat_of(client, gid, bob)
    client.post(f"/api/games/{gid}/night/propose", json={"result_type": "single", "winners": [b]}, headers=h(alice))
    for tok in (bob, carol):
        client.post(f"/api/games/{gid}/night/answer", json={"agree": True}, headers=h(tok))
    entry = view(client, gid, alice)["game"]["night"]["history"][0]
    assert entry["order"] == game1 and entry["order_source"] == "d20" and entry["rolls"] == rolls
    client.post(f"/api/games/{gid}/night/vote", json={"choice": "lobby"}, headers=h(carol))
    lobby = lobby_of(client, gid, alice)
    assert [lobby["seats"][i]["name"] for i in range(3)] == game1  # the lobby keeps last game's order
    preview = lobby["turn_preview"]
    assert preview["source"] == "winner_last" and _names(lobby)[preview["previous_winner"]] == "Bob"
    assert [_names(lobby)[p] for p in preview["order"]] == winner_last(game1, "Bob")
    # the host changes the seating: the others keep the host's order and the winner still goes last
    seating = game1[::-1]
    res = client.post(f"/api/games/{gid}/lobby/arrange", json={"order": _arrangement(lobby, seating)}, headers=h(alice))
    assert res.status_code == 200, res.text
    expected = winner_last(seating, "Bob")
    assert expected != winner_last(game1, "Bob")
    assert [_names(res.json())[p] for p in res.json()["turn_preview"]["order"]] == expected
    for tok in (alice, bob, carol):
        client.post(f"/api/games/{gid}/lobby/ready", json={"ready": True}, headers=h(tok))
    assert client.post(f"/api/games/{gid}/lobby/start", json={}, headers=h(alice)).status_code == 200
    state = hub.get(gid).session.state
    assert [state.players[p].name for p in state.seat_order] == expected and state.turn.active_player == "p1"
    night = view(client, gid, alice)["game"]["night"]
    assert night["number"] == 2 and night["order_source"] == "winner_last" and night["rolls"] == []
    client.post(f"/api/games/{gid}/night/propose", json={"result_type": "draw"}, headers=h(alice))
    for tok in (bob, carol):
        client.post(f"/api/games/{gid}/night/answer", json={"agree": True}, headers=h(tok))
    entry = view(client, gid, alice)["game"]["night"]["history"][1]
    assert entry["order"] == expected and entry["order_source"] == "winner_last" and entry["rolls"] == []
    roundtrip(hub.get(gid).session)


def test_the_final_board_takes_no_undo_request(table):
    """-- final board, quick undo request -- an undo request waiting when the result is recorded can't be approved any more, and a
    new one is refused: the finished table can't change."""
    client, gid, alice, bob = table
    hub = client.app.state.services.hub
    a = seat_of(client, gid, alice)
    act = f"/api/games/{gid}/actions"
    ask = f"/api/games/{gid}/undo-request"
    assert client.post(act, json={"action": {"type": "draw", "player": a, "count": 1}}, headers=h(alice)).status_code == 200
    assert client.post(ask, json={"op": "request"}, headers=h(alice)).status_code == 200  # a draw others saw: the table is asked
    _finish(client, gid, alice, bob, alice)
    room = hub.get(gid)
    before, cursor = board(room.session.state), room.session.history.cursor
    assert client.post(ask, json={"op": "approve"}, headers=h(bob)).status_code == 409
    assert client.post(ask, json={"op": "request"}, headers=h(alice)).status_code == 409
    assert board(room.session.state) == before and room.session.history.cursor == cursor
