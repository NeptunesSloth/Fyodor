"""Game-night hardening (M20): crash recovery with seat reclaim, and idempotent client actions."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import claim_host
from tests.test_protocol_privacy import P1_DECK, P2_DECK


def h(token):
    return {"X-Seat-Token": token}


def lan_table(client):
    a = client.post("/api/decks", json={"text": P1_DECK}).json()["id"]
    b = client.post("/api/decks", json={"text": P2_DECK}).json()["id"]
    game = client.post("/api/games", json={
        "mode": "lan", "password": "friday", "players": [{"name": "Jonathan", "deck_id": a}, {"name": "Mike", "deck_id": b}],
    }).json()
    gid, code = game["game"]["id"], game["game"]["code"]
    host = game["seat"]["token"]
    mike = client.post("/api/join", json={"code": code, "name": "Mike", "password": "friday"}).json()["token"]
    return gid, code, host, mike


def act(client, gid, token, payload, cid=None):
    body = {"action": payload}
    if cid:
        body["client_action_id"] = cid
    return client.post(f"/api/games/{gid}/actions", json=body, headers=h(token))


def table_state(view):
    """What the table shows (the log can gain a 'restored' notice)."""
    return {k: view[k] for k in ("zones", "cards", "turn", "players", "stack")}


def crash(client):
    """Stop without the graceful-shutdown autosave: the process just dies."""
    del client


def test_a_crash_loses_nothing_and_players_keep_their_seats(settings, card_db):
    first = TestClient(create_app(settings))  # no context manager: no lifespan, so no final autosave
    claim_host(first)
    gid, code, host, mike = lan_table(first)
    for payload in ({"type": "draw", "count": 7}, {"type": "life", "player": "p1", "delta": -3}, {"type": "shuffle"}):
        assert act(first, gid, host, payload).status_code == 200
    assert act(first, gid, mike, {"type": "draw", "count": 4}).status_code == 200
    card = first.get(f"/api/games/{gid}/view", headers=h(host)).json()["zones"]["p1:hand"][0]
    act(first, gid, host, {"type": "move", "card_ids": [card], "to": {"zone": "battlefield"}, "x": 100, "y": 100})
    act(first, gid, host, {"type": "tap", "card_ids": [card]})
    first.post(f"/api/games/{gid}/undo", json={}, headers=h(host))  # undo the tap
    before_host = first.get(f"/api/games/{gid}/view", headers=h(host)).json()
    before_mike = first.get(f"/api/games/{gid}/view", headers=h(mike)).json()
    crash(first)

    with TestClient(create_app(settings)) as second:
        claim_host(second)
        # the same seat tokens still work: each player sees exactly their own table again
        after_host = second.get(f"/api/games/{gid}/view", headers=h(host)).json()
        after_mike = second.get(f"/api/games/{gid}/view", headers=h(mike)).json()
        assert table_state(after_host) == table_state(before_host)
        assert table_state(after_mike) == table_state(before_mike)
        assert after_host["cards"][card]["tapped"] is False  # the undo was journaled too
        assert "the table was restored" in json.dumps(after_host["log"])
        # the room code and password still let a spectator in; play simply continues
        spec = second.post("/api/join", json={"code": code, "spectate": True, "password": "friday"})
        assert spec.status_code == 200, spec.text
        assert act(second, gid, mike, {"type": "life", "player": "p2", "delta": -1}).status_code == 200
        # undo still reaches back past the crash (the life change, then the move from before it)
        assert second.post(f"/api/games/{gid}/undo", json={}, headers=h(mike)).status_code == 200
        assert second.post(f"/api/games/{gid}/undo", json={}, headers=h(mike)).status_code == 200
        # -- quick undo request -- and the journal kept what each action showed: Mike's draw asks the table first
        res = second.post(f"/api/games/{gid}/undo", json={}, headers=h(mike))
        assert res.status_code == 409 and "take back a draw" in res.json()["detail"]


def test_closed_tables_are_not_brought_back(settings, card_db):
    first = TestClient(create_app(settings))
    claim_host(first)
    gid, _, host, _ = lan_table(first)
    assert first.delete(f"/api/games/{gid}").status_code in (200, 204)
    crash(first)
    with TestClient(create_app(settings)) as second:
        claim_host(second)
        assert second.get(f"/api/games/{gid}/view", headers=h(host)).status_code in (403, 404)


def test_a_graceful_restart_also_restores_the_table(settings, card_db):
    with TestClient(create_app(settings)) as first:
        claim_host(first)
        gid, _, host, _ = lan_table(first)
        act(first, gid, host, {"type": "draw", "count": 2})
    with TestClient(create_app(settings)) as second:
        claim_host(second)
        view = second.get(f"/api/games/{gid}/view", headers=h(host)).json()
        assert len(view["zones"]["p1:hand"]) == 2


def test_a_retried_action_is_applied_once(settings, card_db):
    first = TestClient(create_app(settings))
    claim_host(first)
    gid, _, host, _ = lan_table(first)
    one = act(first, gid, host, {"type": "life", "player": "p1", "delta": -1}, cid="c-0001-life")
    two = act(first, gid, host, {"type": "life", "player": "p1", "delta": -1}, cid="c-0001-life")
    assert one.json()["status"] == "ACCEPTED" and two.json()["status"] == "ALREADY_APPLIED"
    life = next(p["life"] for p in two.json()["players"] if p["id"] == "p1")
    assert life == 39
    bad = act(first, gid, host, {"type": "tap", "card_ids": ["nope"]}, cid="c-0002-bad")
    assert bad.status_code in (404, 409, 422)
    again = act(first, gid, host, {"type": "tap", "card_ids": ["nope"]}, cid="c-0002-bad")
    assert again.json()["status"] == "ALREADY_APPLIED" and again.json()["outcome"].startswith("REJECTED")
    crash(first)
    # ids survive a crash: a client retrying after the restart still gets ALREADY_APPLIED
    with TestClient(create_app(settings)) as second:
        claim_host(second)
        res = act(second, gid, host, {"type": "life", "player": "p1", "delta": -1}, cid="c-0001-life")
        assert res.json()["status"] == "ALREADY_APPLIED"
        assert next(p["life"] for p in res.json()["players"] if p["id"] == "p1") == 39


def test_client_action_ids_are_validated(client):
    gid, _, host, _ = lan_table(client)
    res = client.post(f"/api/games/{gid}/actions", json={"action": {"type": "draw"}, "client_action_id": "../../x"}, headers=h(host))
    assert res.status_code == 422


def test_websocket_retries_are_idempotent(client):
    gid, _, host, _ = lan_table(client)
    with client.websocket_connect(f"/ws/games/{gid}?token={host}") as ws:
        ws.receive_json()
        msg = {"type": "action", "id": 1, "client_action_id": "ws-action-0001", "action": {"type": "draw", "count": 1}}
        def ack(i):
            for _ in range(10):  # state broadcasts may arrive around the ack
                r = ws.receive_json()
                if r.get("type") in ("ack", "error") and r.get("id") == i:
                    return r
            raise AssertionError("no ack")

        ws.send_json(msg)
        assert ack(1)["status"] == "ACCEPTED"
        ws.send_json({**msg, "id": 2})
        assert ack(2) == {"type": "ack", "id": 2, "status": "ALREADY_APPLIED"}
    view = client.get(f"/api/games/{gid}/view", headers=h(host)).json()
    assert len(view["zones"]["p1:hand"]) == 1


def test_a_same_decks_rematch_still_works_after_a_crash(settings, card_db):
    """-- restart rematch -- the crash record keeps every seat's deck, so "Rematch — same decks" isn't refused after a restart."""
    first = TestClient(create_app(settings))
    claim_host(first)
    gid, code, host, mike = lan_table(first)
    assert act(first, gid, host, {"type": "draw", "count": 1}).status_code == 200
    crash(first)

    with TestClient(create_app(settings)) as second:
        claim_host(second)
        night = second.get(f"/api/games/{gid}/view", headers=h(host)).json()["game"]["night"]
        assert night["rematch_missing"] == []
        assert "Counterspell" not in json.dumps(night)  # (only seat names are public, never a card)
        assert second.post(f"/api/games/{gid}/night/propose", json={"result_type": "draw"}, headers=h(host)).status_code == 200
        assert second.post(f"/api/games/{gid}/night/answer", json={"agree": True}, headers=h(mike)).status_code == 200
        assert second.post(f"/api/games/{gid}/night/vote", json={"choice": "rematch"}, headers=h(host)).status_code == 200
        res = second.post(f"/api/games/{gid}/night/vote", json={"choice": "rematch"}, headers=h(mike))
        assert res.status_code == 200 and res.json()["decision"] == "rematch", res.text
        v = second.get(f"/api/games/{gid}/view", headers=h(mike)).json()
        assert v["game"]["night"]["number"] == 2
        assert {c["name"] for p in v["players"] for c in p["commanders"]} == {"Atraxa, Praetors' Voice", "Krenko, Mob Boss"}


def test_a_rematch_the_table_cant_start_is_refused_before_the_vote_counts(settings, card_db):
    """-- restart rematch -- a record without the decks (saved before they were kept): the view says so, and a rematch vote is
    refused without being stored (it used to be kept and shown as "Deciding…")."""
    with TestClient(create_app(settings)) as client:
        claim_host(client)
        gid, code, host, mike = lan_table(client)
        client.app.state.services.hub.get(gid).night.setups = {}
        assert client.post(f"/api/games/{gid}/night/propose", json={"result_type": "draw"}, headers=h(host)).status_code == 200
        assert client.post(f"/api/games/{gid}/night/answer", json={"agree": True}, headers=h(mike)).status_code == 200
        night = client.get(f"/api/games/{gid}/view", headers=h(host)).json()["game"]["night"]
        assert night["rematch_missing"] == ["Jonathan", "Mike"]
        res = client.post(f"/api/games/{gid}/night/vote", json={"choice": "rematch"}, headers=h(mike))
        assert res.status_code == 409 and "return to the lobby" in res.json()["detail"]
        assert client.get(f"/api/games/{gid}/view", headers=h(host)).json()["game"]["night"]["votes"] == {}
