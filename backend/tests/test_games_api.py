from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.game.visibility import OMNISCIENT
from tests.conftest import claim_host, connect_game, guest

KRENKO = """Commander
1 Krenko, Mob Boss
Deck
1 Sol Ring
1 Lightning Bolt
1 Llanowar Elves
20 Mountain
"""
ATRAXA = """Commander
1 Atraxa, Praetors' Voice
Deck
1 Counterspell
1 Arcane Signet
20 Island
"""


@pytest.fixture()
def decks(client):
    a = client.post("/api/decks", json={"text": KRENKO}).json()["id"]
    b = client.post("/api/decks", json={"text": ATRAXA}).json()["id"]
    return a, b


def create(client, decks, **extra):
    body = {"name": "Test game", "players": [{"name": "Alice", "deck_id": decks[0]}, {"name": "Bob", "deck_id": decks[1]}]}
    body.update(extra)
    res = client.post("/api/games", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def act(client, game_id, action, **kw):
    headers = {"X-Seat-Token": kw.pop("token")} if "token" in kw else {}
    return client.post(f"/api/games/{game_id}/actions", json={"action": action, **kw}, headers=headers)


def test_commander_is_the_default_and_constructed_is_refused(client, decks):
    """A new table is Commander (40 life) unless the host picks Sandbox; Constructed was removed and stays refused."""
    game = create(client, decks, mode="lan", automation="full")
    gid = game["game"]["id"]
    assert game["game"]["format"] == "commander"
    view = client.get(f"/api/games/{gid}/view", headers={"X-Seat-Token": game["seat"]["token"]}).json()
    assert view["game"]["format"] == "commander" and view["players"][0]["life"] == 40
    assert view["game"]["settings"]["automation"] == "full" and not view["game"]["settings"]["allow_test_objects"]
    body = {"name": "T", "format": "constructed", "players": [{"name": "Alice", "deck_id": decks[0]}]}
    assert client.post("/api/games", json=body).status_code == 422


def test_a_sandbox_table_is_free_play(client, decks):
    """Sandbox (free play, as in Tabletop Simulator): Commander decks at 40 life, rules automation off whatever was asked for,
    and test objects allowed. The host can still turn automation on at the table, and the starting life stays editable."""
    game = create(client, decks, mode="lan", format="sandbox", automation="full", players=[{"name": "Alice", "deck_id": decks[0]}])
    gid, token = game["game"]["id"], game["seat"]["token"]
    assert game["game"]["format"] == "sandbox"
    view = client.get(f"/api/games/{gid}/view", headers={"X-Seat-Token": token}).json()
    assert view["game"]["format"] == "sandbox" and view["players"][0]["life"] == 40
    settings = view["game"]["settings"]
    assert settings["automation"] == "off" and settings["allow_test_objects"] and view.get("rules") is None
    assert len(view["zones"]["p1:command"]) == 1  # still a Commander deck: the commander waits in the command zone
    bears = client.app.state.services.cards.resolve("Sol Ring")["id"]
    spawned = act(client, gid, {"type": "spawn_card", "card_id": bears}, token=token)
    assert spawned.status_code == 200, spawned.text
    on = act(client, gid, {"type": "configure", "automation": "full"}, token=token)  # the host turns the rules on at the table
    assert on.status_code == 200, on.text
    assert on.json()["game"]["settings"]["automation"] == "full"

    other = create(client, decks, mode="lan", format="sandbox", starting_life=25)
    view = client.get(f"/api/games/{other['game']['id']}/view", headers={"X-Seat-Token": other["seat"]["token"]}).json()
    assert view["players"][0]["life"] == 25


def test_a_sandbox_game_saves_and_loads(client, decks):
    game = create(client, decks, mode="lan", format="sandbox")
    gid, token = game["game"]["id"], game["seat"]["token"]
    act(client, gid, {"type": "draw", "count": 3}, token=token)
    saved = client.post(f"/api/games/{gid}/save", json={"name": "Free play"}, headers={"X-Seat-Token": token})
    assert saved.status_code == 201, saved.text
    saved = saved.json()
    loaded = client.post(f"/api/saves/{saved['id']}/load", json={"mode": "lan"})
    assert loaded.status_code == 201, loaded.text
    body = loaded.json()
    assert body["game"]["format"] == "sandbox"
    view = client.get(f"/api/games/{body['game']['id']}/view", headers={"X-Seat-Token": body["seat"]["token"]}).json()
    assert view["game"]["format"] == "sandbox" and len(view["zones"]["p1:hand"]) == 3 and view["game"]["can_undo"]


def test_local_game_flow(client, decks):
    game = create(client, decks)
    gid = game["game"]["id"]
    view = client.get(f"/api/games/{gid}/view", params={"viewer": "p1"}).json()
    assert view["players"][0]["life"] == 40
    assert view["zones"]["p1:library"]["count"] == 23
    assert len(view["zones"]["p1:command"]) == 1

    res = act(client, gid, {"type": "draw", "count": 7}, **{"as": "p1", "viewer": "p1"})
    assert res.status_code == 200
    assert len(res.json()["zones"]["p1:hand"]) == 7
    assert res.json()["game"]["can_undo"] is True

    # hot-seat: act as p2 and view as p2
    res = act(client, gid, {"type": "life", "delta": -3}, **{"as": "p2", "viewer": "p2"})
    assert res.json()["players"][1]["life"] == 37
    hand = res.json()["zones"]["p1:hand"]
    assert all(res.json()["cards"][c]["hidden"] for c in hand)

    res = client.post(f"/api/games/{gid}/undo", json={"as": "p2", "viewer": "p2"})
    assert res.json()["players"][1]["life"] == 40
    res = client.post(f"/api/games/{gid}/redo", json={"as": "p2"})
    assert res.json()["players"][1]["life"] == 37

    all_view = client.get(f"/api/games/{gid}/view", params={"viewer": "all"}).json()
    assert all_view["viewer"] == OMNISCIENT


def test_action_errors_are_reported(client, decks):
    gid = create(client, decks)["game"]["id"]
    res = act(client, gid, {"type": "draw", "count": 999})
    assert res.status_code == 422
    res = act(client, gid, {"type": "tap", "card_ids": ["nope"]})
    assert res.status_code == 409 and "not in this game" in res.json()["detail"]
    res = act(client, gid, {"type": "bogus"})
    assert res.status_code == 422


def test_local_games_refuse_remote_clients(client, decks, settings):
    gid = create(client, decks)["game"]["id"]
    remote = client.get(f"/api/games/{gid}/view", headers=guest())
    assert remote.status_code == 403
    assert client.get("/api/games", headers=guest()).json() == []
    assert client.get("/api/saves", headers=guest()).status_code == 403
    body = {"players": [{"name": "Mallory"}]}
    assert client.post("/api/games", json=body, headers=guest()).status_code == 403


def test_lan_join_and_private_views(client, decks):
    game = create(client, decks, mode="lan", password="hunter2")
    gid, code = game["game"]["id"], game["game"]["code"]
    host_token = game["seat"]["token"]
    assert game["seat"]["player_id"] == "p1"

    remote = guest()
    assert client.post("/api/join", json={"code": code, "password": "wrong"}, headers=remote).status_code == 403
    joined = client.post("/api/join", json={"code": code, "password": "hunter2", "name": "Bobby"}, headers=remote).json()
    assert joined["viewer"] == "p2"
    bob = joined["token"]
    # table full -> seat conflict, but spectating is fine
    assert client.post("/api/join", json={"code": code, "password": "hunter2"}, headers=remote).status_code == 409
    spec = client.post("/api/join", json={"code": code, "password": "hunter2", "spectate": True}, headers=remote).json()

    # no token -> no view
    assert client.get(f"/api/games/{gid}/view", headers=remote).status_code == 403
    # each seat acts as itself only (the "as" field is ignored in LAN games)
    res = act(client, gid, {"type": "draw", "count": 7}, token=host_token, **{"as": "p2"})
    assert res.status_code == 200
    alice_view = res.json()
    assert len(alice_view["zones"]["p1:hand"]) == 7 and alice_view["viewer"] == "p1"

    bob_view = client.get(f"/api/games/{gid}/view", headers={"X-Seat-Token": bob, **remote}).json()
    assert bob_view["viewer"] == "p2"
    assert bob_view["players"][1]["name"] == "Bobby"
    names_in_alice_hand = {alice_view["cards"][c]["name"] for c in alice_view["zones"]["p1:hand"]}
    bob_text = json.dumps({k: v for k, v in bob_view.items() if k != "log"})
    for cid in bob_view["zones"]["p1:hand"]:
        assert bob_view["cards"][cid] == {"id": cid, "hidden": True, "owner": "p1", "controller": "p1",
                                          "zone": "p1:hand", "face_down": False}
    for name in names_in_alice_hand - {"Mountain"}:
        assert name not in bob_text

    spec_view = client.get(f"/api/games/{gid}/view", headers={"X-Seat-Token": spec["token"], **remote}).json()
    assert spec_view["viewer"] == "__spectator__"
    res = act(client, gid, {"type": "draw"}, token=spec["token"])
    assert res.status_code == 403
    # a remote client cannot request the omniscient view
    res = client.get(f"/api/games/{gid}/view", params={"viewer": "all"}, headers={"X-Seat-Token": bob, **remote})
    assert res.json()["viewer"] == "p2"


def test_private_diagnostics_keep_a_lan_game_in_progress_out(client, decks):
    """The host computer's diagnostics export can't show other players' hands mid-game; once the result is recorded it can."""
    game = create(client, decks, mode="lan")
    gid, code = game["game"]["id"], game["game"]["code"]
    bob = client.post("/api/join", json={"code": code}, headers=guest()).json()["token"]
    bob_hand = act(client, gid, {"type": "draw", "count": 7}, token=bob).json()["zones"]["p2:hand"]

    room = next(r for r in client.get("/api/diagnostics?include_private=true").json()["rooms"] if r["id"] == gid)
    assert "state" not in room and "still being played" in room["state_withheld"]
    assert not any(c in client.get("/api/diagnostics?include_private=true").text for c in bob_hand)

    client.app.state.services.hub.rooms[gid].result_id = "recorded"  # the game ended and its result was recorded
    room = next(r for r in client.get("/api/diagnostics?include_private=true").json()["rooms"] if r["id"] == gid)
    assert "state_withheld" not in room and set(bob_hand) <= set(room["state"]["zones"]["p2:hand"])


def test_lan_host_computer_never_gets_the_all_hands_view(client, decks):
    """The host's own computer sees a LAN table like a spectator: no hidden card reaches it (REST or WebSocket)."""
    game = create(client, decks, mode="lan")
    gid, code, host = game["game"]["id"], game["game"]["code"], game["host_token"]
    remote = guest()
    bob = client.post("/api/join", json={"code": code}, headers=remote).json()["token"]
    res = act(client, gid, {"type": "draw", "count": 7}, token=bob)
    assert res.status_code == 200
    bob_hand = res.json()["zones"]["p2:hand"]

    view = client.get(f"/api/games/{gid}/view", params={"viewer": "all"}, headers={"X-Seat-Token": host}).json()
    assert view["viewer"] == "__spectator__"
    assert len(view["zones"]["p2:hand"]) == 7 and all(view["cards"][c].get("hidden") for c in view["zones"]["p2:hand"])
    assert not set(bob_hand) & set(json.dumps(view).split('"'))  # not even the hidden cards' ids
    with connect_game(client, gid, host, viewer='all') as ws:
        first = ws.receive_json()
        assert first["type"] == "state" and first["view"]["viewer"] == "__spectator__"
        assert all(first["view"]["cards"][c].get("hidden") for c in first["view"]["zones"]["p2:hand"])
    # hot-seat tables on one computer keep the open-table view
    local = create(client, decks)["game"]["id"]
    assert client.get(f"/api/games/{local}/view", params={"viewer": "all"}).json()["viewer"] == OMNISCIENT


def test_join_brute_force_throttled(client, decks):
    create(client, decks, mode="lan", password="pw")
    headers = guest()
    codes = [client.post("/api/join", json={"code": "ZZZZZZ"}, headers=headers).status_code for _ in range(7)]
    assert codes == [403] * 5 + [429] * 2


def test_websocket_sync_and_hidden_info(client, decks):
    game = create(client, decks, mode="lan")
    gid, code = game["game"]["id"], game["game"]["code"]
    alice = game["seat"]["token"]
    bob = client.post("/api/join", json={"code": code}).json()["token"]
    with connect_game(client, gid, alice) as wa, connect_game(client, gid, bob) as wb:
        first_a = wa.receive_json()
        assert first_a["type"] == "state" and first_a["view"]["viewer"] == "p1"
        wb.receive_json()
        wa.receive_json()  # broadcast after bob connected
        wa.send_json({"type": "action", "action": {"type": "draw", "count": 7}, "id": 1})
        msgs = [wa.receive_json(), wa.receive_json()]
        assert {"type": "ack", "id": 1, "status": "ACCEPTED"} in msgs
        state_a = next(m for m in msgs if m["type"] == "state")["view"]
        assert all("name" in state_a["cards"][c] for c in state_a["zones"]["p1:hand"])
        state_b = wb.receive_json()
        while state_b["type"] != "state" or state_b["view"]["game"]["seq"] < 1:
            state_b = wb.receive_json()
        assert all(state_b["view"]["cards"][c].get("hidden") for c in state_b["view"]["zones"]["p1:hand"])

        wb.send_json({"type": "action", "action": {"type": "nonsense"}, "id": 2})
        err = wb.receive_json()
        assert err["type"] == "error" and err["id"] == 2
        wb.send_text("{not json")
        assert wb.receive_json()["type"] == "error"
        wb.send_json({"type": "view", "viewer": "all"})
        assert "Cannot change seats" in wb.receive_json()["message"]

    with connect_game(client, gid, 'forged') as ws, pytest.raises(WebSocketDisconnect) as closed:
        ws.receive_json()
    assert closed.value.code == 4403


def test_save_load_and_autosave(client, decks, settings):
    gid = create(client, decks)["game"]["id"]
    act(client, gid, {"type": "draw", "count": 7})
    act(client, gid, {"type": "shuffle"}, **{"as": "p2"})
    act(client, gid, {"type": "life", "delta": -4})
    before = client.get(f"/api/games/{gid}/view", params={"viewer": "all"}).json()
    saved = client.post(f"/api/games/{gid}/save", json={"name": "Mid game"}).json()
    assert saved["name"] == "Mid game" and saved["players"][0]["life"] == 36

    saves = client.get("/api/saves").json()
    assert any(s["autosave"] for s in saves)  # created on game start
    assert client.delete(f"/api/games/{gid}").status_code == 204
    assert client.get(f"/api/games/{gid}").status_code == 404

    loaded = client.post(f"/api/saves/{saved['id']}/load", json={}).json()
    gid2 = loaded["game"]["id"]
    after = client.get(f"/api/games/{gid2}/view", params={"viewer": "all"}).json()
    for key in ("players", "zones", "cards", "turn", "table"):
        assert after[key] == before[key]
    # history survives the round trip: undo the life change
    res = client.post(f"/api/games/{gid2}/undo", json={})
    assert res.json()["players"][0]["life"] == 40
    assert client.delete(f"/api/saves/{saved['id']}").status_code == 204


def test_save_survives_restart(settings, card_db, decks, client):
    gid = create(client, decks)["game"]["id"]
    act(client, gid, {"type": "life", "delta": -1})
    client.post(f"/api/games/{gid}/save", json={"name": "persist"})
    from app.main import create_app

    with TestClient(create_app(settings)) as fresh:
        claim_host(fresh)
        saves = [s for s in fresh.get("/api/saves").json() if s["name"] == "persist"]
        assert saves
        gid2 = fresh.post(f"/api/saves/{saves[0]['id']}/load", json={}).json()["game"]["id"]
        assert fresh.get(f"/api/games/{gid2}/view").json()["players"][0]["life"] == 39


def test_corrupt_save_rejected(client, settings, decks):
    gid = create(client, decks)["game"]["id"]
    saved = client.post(f"/api/games/{gid}/save", json={}).json()
    services = client.app.state.services
    services.app_db.execute("UPDATE saves SET payload = ? WHERE id = ?", (b"garbage", saved["id"]))
    services.app_db.commit()
    res = client.post(f"/api/saves/{saved['id']}/load", json={})
    assert res.status_code == 422


def test_load_a_new_deck_at_the_table_without_leaving(client, decks):
    """The scripted tables' importer: paste a list (or pick a saved deck) and it replaces your deck mid-game."""
    gid = create(client, decks)["game"]["id"]

    def view(v="p1"):
        return client.get(f"/api/games/{gid}/view", params={"viewer": v}).json()

    client.post(f"/api/games/{gid}/actions", json={"action": {"type": "draw", "player": "p1", "count": 3}})
    before = view()
    old_ids = {cid for cid, c in before["cards"].items() if c.get("owner") == "p1"}
    res = client.post(f"/api/games/{gid}/load-deck", json={"text": ATRAXA, "name": "Superfriends"})
    assert res.status_code == 200, res.text
    after = view()
    me = next(p for p in after["players"] if p["id"] == "p1")
    assert me["deck_name"] == "Superfriends" and me["life"] == 40 and me["hand_count"] == 7
    assert [c["name"] for c in me["commanders"]] == ["Atraxa, Praetors' Voice"]
    assert after["zones"]["p1:library"]["count"] == 22 - 7
    assert not old_ids & set(after["cards"])  # the old deck's cards left the table
    assert "placed a new deck" in json.dumps(after["log"][-1])
    # Bob's seat is untouched; the host's saved decks work too, and a client can't send the action itself
    assert next(p for p in after["players"] if p["id"] == "p2")["deck_name"] == before["players"][1]["deck_name"]
    assert client.post(f"/api/games/{gid}/load-deck", json={"deck_id": decks[0], "draw": 0}).status_code == 200
    assert next(p for p in view()["players"] if p["id"] == "p1")["hand_count"] == 0
    forged = client.post(f"/api/games/{gid}/actions", json={"action": {"type": "load_deck", "player": "p1", "cards": [{"section": "main", "quantity": 1, "name": "Island"}]}})
    assert forged.status_code in (400, 409, 422)
    # it can be undone like any action
    assert client.post(f"/api/games/{gid}/undo", json={}).status_code in (200, 204)
    assert next(p for p in view()["players"] if p["id"] == "p1")["deck_name"] == "Superfriends"


def test_play_page_tiles_name_each_players_commanders(client, decks):
    """The Play page shows tables and saves with their commanders: public once the game starts (903.6), but listed on the
    host's own screen only; another LAN device sees names until it sits at a table, and a lobby has none yet."""
    gid = create(client, decks)["game"]["id"]
    listed = next(g for g in client.get("/api/games").json() if g["id"] == gid)
    assert [p["commanders"][0]["name"] for p in listed["players"]] == ["Krenko, Mob Boss", "Atraxa, Praetors' Voice"]
    assert all(p["commanders"][0]["card_id"] for p in listed["players"]) and listed["players"][0]["color"]

    remote = guest()
    locked = create(client, decks, mode="lan", password="hunter2")["game"]["id"]
    open_ = create(client, decks, mode="lan")["game"]["id"]
    seen = {g["id"]: g for g in client.get("/api/games", headers=remote).json()}
    assert seen.keys() >= {locked, open_}
    assert all("commanders" not in p and "color" not in p for g in seen.values() for p in g["players"])
    assert "Atraxa" not in json.dumps(list(seen.values()))
    assert next(g for g in client.get("/api/games").json() if g["id"] == open_)["players"][1]["commanders"]
    lobby = client.post("/api/games", json={"name": "Night", "mode": "lan", "lobby": True, "players": [{"name": "Host"}]}).json()
    assert all("commanders" not in p for p in seen.get(lobby["game"]["id"], lobby["game"])["players"])
    assert client.get(f"/api/games/{gid}").json()["players"][0].keys() == {"id", "name", "claimed", "connected"}

    saved = client.post(f"/api/games/{gid}/save", json={"name": "Tiles"}).json()
    assert saved["players"][1]["commanders"][0]["name"] == "Atraxa, Praetors' Voice"
    assert saved["players"][0]["color"] == listed["players"][0]["color"]
    row = next(s for s in client.get("/api/saves").json() if s["id"] == saved["id"])
    assert row["players"] == saved["players"]
    # the save still loads, and the loaded table lists the same commanders
    loaded = client.post(f"/api/saves/{saved['id']}/load", json={}).json()["game"]["id"]
    again = next(g for g in client.get("/api/games").json() if g["id"] == loaded)
    assert [p["commanders"] for p in again["players"]] == [p["commanders"] for p in listed["players"]]
