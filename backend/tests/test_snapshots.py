"""Named table snapshots and the history view: exact restores, undoable, private info kept private."""

from __future__ import annotations

import json

import pytest

from tests.test_protocol_privacy import P1_DECK, P2_DECK


@pytest.fixture()
def table(client):
    a = client.post("/api/decks", json={"text": P1_DECK}).json()["id"]
    b = client.post("/api/decks", json={"text": P2_DECK}).json()["id"]
    game = client.post("/api/games", json={"mode": "lan", "players": [{"name": "Alice", "deck_id": a}, {"name": "Bob", "deck_id": b}]}).json()
    gid = game["game"]["id"]
    alice = game["seat"]["token"]
    bob = client.post("/api/join", json={"code": game["game"]["code"], "name": "Bob"}).json()["token"]
    return client, gid, alice, bob


def h(t):
    return {"X-Seat-Token": t}


def act(client, gid, token, action):
    res = client.post(f"/api/games/{gid}/actions", json={"action": action}, headers=h(token))
    assert res.status_code == 200, res.text
    return res.json()


def state(client, gid):
    return client.app.state.services.hub.get(gid).session.state


def core(st):
    d = st.model_dump(mode="json")
    return {k: d[k] for k in ("cards", "zones", "players", "turn", "table", "arrows")}


def test_snapshot_restore_is_exact_undoable_and_private(table):
    client, gid, alice, bob = table
    act(client, gid, alice, {"type": "draw", "count": 5})
    hand = list(state(client, gid).zones["p1:hand"])
    act(client, gid, alice, {"type": "move", "card_ids": [hand[0]], "to": {"zone": "battlefield"}, "x": 10, "y": 10})
    act(client, gid, alice, {"type": "counter", "card_ids": [hand[0]], "kind": "+1/+1", "delta": 2})
    act(client, gid, alice, {"type": "add_effect", "card_ids": [hand[0]], "name": "Flying"})
    before = core(state(client, gid))
    snap = client.post(f"/api/games/{gid}/snapshots", json={"name": "Before board wipe"}, headers=h(bob)).json()
    assert snap["name"] == "Before board wipe" and "state" not in snap
    # wreck the table
    act(client, gid, alice, {"type": "move", "card_ids": [hand[0]], "to": {"zone": "graveyard"}})
    act(client, gid, alice, {"type": "shuffle"})
    act(client, gid, bob, {"type": "life", "player": "p2", "delta": -15})
    assert core(state(client, gid)) != before
    # only the host restores
    assert client.post(f"/api/games/{gid}/snapshots/{snap['id']}/restore", headers=h(bob)).status_code == 403
    view = client.post(f"/api/games/{gid}/snapshots/{snap['id']}/restore", headers=h(alice)).json()
    assert core(state(client, gid)) == before  # cards, zones, library order, counters, effects, life …
    assert "restored the table: snapshot “Before board wipe”" in json.dumps(view["log"], ensure_ascii=False)
    # hidden information is still hidden after restoring
    bob_view = client.get(f"/api/games/{gid}/view", headers=h(bob)).json()
    for cid in state(client, gid).zones["p1:hand"] + state(client, gid).zones["p1:library"]:
        assert cid not in json.dumps({k: v for k, v in bob_view.items() if k != "log"})
    # the restore is an ordinary action: undo and redo
    client.post(f"/api/games/{gid}/undo", json={}, headers=h(alice))
    assert state(client, gid).players["p2"].life == 25
    client.post(f"/api/games/{gid}/redo", json={}, headers=h(alice))
    assert core(state(client, gid)) == before


def test_clients_cannot_forge_a_restore(table):
    client, gid, alice, bob = table
    forged = {"type": "restore_state", "label": "x", "state": state(client, gid).model_dump(mode="json")}
    res = client.post(f"/api/games/{gid}/actions", json={"action": forged}, headers=h(alice))
    assert res.status_code == 409 and "snapshots or history" in res.json()["detail"]


def test_snapshots_are_saved_with_the_game(table):
    client, gid, alice, bob = table
    client.post(f"/api/games/{gid}/snapshots", json={"name": "Turn 1"}, headers=h(alice))
    save = client.post(f"/api/games/{gid}/save", json={"name": "s"}, headers=h(alice)).json()
    client.delete(f"/api/games/{gid}")
    body = client.post(f"/api/saves/{save['id']}/load", json={"mode": "lan"}).json()
    token = body["seat"]["token"]
    snaps = client.get(f"/api/games/{gid}/snapshots", headers=h(token)).json()
    assert [s["name"] for s in snaps] == ["Turn 1"]
    assert client.post(f"/api/games/{gid}/snapshots/{snaps[0]['id']}/restore", headers=h(token)).status_code == 200


def test_history_lists_events_per_viewer_and_shows_past_states(table):
    client, gid, alice, bob = table
    act(client, gid, alice, {"type": "draw", "count": 3})
    act(client, gid, alice, {"type": "life", "player": "p1", "delta": -2})
    act(client, gid, alice, {"type": "roll", "sides": 20})
    hist = client.get(f"/api/games/{gid}/history", headers=h(bob)).json()
    assert [i["type"] for i in hist["items"]] == ["rename_player", "draw", "life", "roll"] and hist["cursor"] == 4
    names = {c.name for c in state(client, gid).cards.values() if c.zone == "p1:hand"}
    assert not any(n in json.dumps(hist) for n in names)  # Bob never learns Alice's draws
    past = client.get(f"/api/games/{gid}/history/2", headers=h(bob)).json()
    assert past["players"][0]["life"] == 40 and len(past["zones"]["p1:hand"]) == 3
    assert all(past["cards"][cid].get("hidden") for cid in past["zones"]["p1:hand"])
    mine = client.get(f"/api/games/{gid}/history/2", headers=h(alice)).json()
    assert not any(mine["cards"][cid].get("hidden") for cid in mine["zones"]["p1:hand"])
    # restore from here (host)
    assert client.post(f"/api/games/{gid}/history/2/restore", headers=h(bob)).status_code == 403
    client.post(f"/api/games/{gid}/history/2/restore", headers=h(alice))
    assert state(client, gid).players["p1"].life == 40 and len(state(client, gid).zones["p1:hand"]) == 3
    # the dice result is recorded in the action, so redo never rerolls
    roll = client.app.state.services.hub.get(gid).session.history.actions[3]
    assert roll.r is not None
