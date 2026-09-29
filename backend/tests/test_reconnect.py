"""Reconnect, presence, revisions/resync and the host's repair tools."""

from __future__ import annotations

import time

import pytest
from starlette.websockets import WebSocketDisconnect

from app.game.errors import ActionError
from tests.game_helpers import act, find, make_session, zone
from tests.test_protocol_privacy import P1_DECK, P2_DECK


@pytest.fixture()
def table(client):
    a = client.post("/api/decks", json={"text": P1_DECK}).json()["id"]
    b = client.post("/api/decks", json={"text": P2_DECK}).json()["id"]
    game = client.post("/api/games", json={
        "mode": "lan", "players": [{"name": "Jonathan", "deck_id": a}, {"name": "Mike", "deck_id": b}],
    }).json()
    gid, code = game["game"]["id"], game["game"]["code"]
    host = game["seat"]["token"]
    mike = client.post("/api/join", json={"code": code, "name": "Mike"}).json()["token"]
    return client, gid, host, mike


def h(token):
    return {"X-Seat-Token": token}


def view(client, gid, token):
    res = client.get(f"/api/games/{gid}/view", headers=h(token))
    assert res.status_code == 200, res.text
    return res.json()


def action(client, gid, token, payload):
    return client.post(f"/api/games/{gid}/actions", json={"action": payload}, headers=h(token))


def test_reconnect_restores_same_seat_hand_and_presence(table):
    client, gid, host, mike = table
    action(client, gid, mike, {"type": "draw", "count": 5})
    hand = view(client, gid, mike)["zones"]["p2:hand"]
    with client.websocket_connect(f"/ws/games/{gid}?token={mike}") as ws:
        first = ws.receive_json()
        assert first["view"]["viewer"] == "p2" and first["view"]["zones"]["p2:hand"] == hand
        assert view(client, gid, host)["game"]["seats"]["p2"]["presence"] == "connected"
    # dropped: others see "reconnecting" (and nothing about his hand)
    host_view = view(client, gid, host)
    assert host_view["game"]["seats"]["p2"]["presence"] == "reconnecting"
    assert all(i not in str(host_view) for i in hand)
    # comes back with the same token: same seat, same hand, same permissions
    with client.websocket_connect(f"/ws/games/{gid}?token={mike}") as ws:
        again = ws.receive_json()
        assert again["view"]["viewer"] == "p2" and again["view"]["zones"]["p2:hand"] == hand
    # after the grace period: disconnected
    seat = client.app.state.services.hub.get(gid).seats["p2"]
    seat.last_seen = time.time() - 3600
    assert view(client, gid, host)["game"]["seats"]["p2"]["presence"] == "disconnected"
    assert view(client, gid, host)["game"]["seats"]["p1"]["presence"] == "disconnected"  # never connected by socket


def test_revisions_increase_and_resync_replaces_state(table):
    client, gid, host, mike = table
    with client.websocket_connect(f"/ws/games/{gid}?token={mike}") as ws:
        first = ws.receive_json()
        rev = first["revision"]
        ws.receive_json()  # presence broadcast
        ws.send_json({"type": "action", "action": {"type": "draw"}, "id": 1})
        msgs = [ws.receive_json(), ws.receive_json()]
        state = next(m for m in msgs if m["type"] == "state")
        assert state["revision"] > rev and state["view"]["game"]["revision"] == state["revision"]
        ws.send_json({"type": "resync", "id": 2})
        resynced = ws.receive_json()
        assert resynced["resync"] and resynced["view"]["zones"]["p2:hand"] == state["view"]["zones"]["p2:hand"]
        # the host can resync everybody; a guest can't
        assert client.post(f"/api/games/{gid}/host/resync", headers=h(mike)).status_code == 403
        assert client.post(f"/api/games/{gid}/host/resync", headers=h(host)).status_code == 200
        assert ws.receive_json()["resync"] is True


def test_seat_link_reassigns_a_seat_and_revokes_the_old_token(table):
    client, gid, host, mike = table
    action(client, gid, mike, {"type": "draw", "count": 3})
    hand = view(client, gid, mike)["zones"]["p2:hand"]
    assert client.post(f"/api/games/{gid}/host/seat-link", json={"seat": "p2"}, headers=h(mike)).status_code == 403
    res = client.post(f"/api/games/{gid}/host/seat-link", json={"seat": "p2"}, headers=h(host)).json()
    assert res["path"].endswith(f"seat_token={res['token']}")
    assert client.get(f"/api/games/{gid}/view", headers=h(mike)).status_code == 403
    new = view(client, gid, res["token"])
    assert new["viewer"] == "p2" and new["zones"]["p2:hand"] == hand


def test_force_reconnect_closes_the_socket_with_a_retry_code(table):
    client, gid, host, mike = table
    with client.websocket_connect(f"/ws/games/{gid}?token={mike}") as ws:
        ws.receive_json()
        ws.receive_json()
        assert client.post(f"/api/games/{gid}/host/reconnect", json={"seat": "p2"}, headers=h(host)).json()["dropped"] == 1
        with pytest.raises(WebSocketDisconnect) as info:
            for _ in range(5):
                ws.receive_json()
        assert info.value.code == 4000


def test_remove_player_is_host_only_and_their_cards_leave(table):
    client, gid, host, mike = table
    state = client.app.state.services.hub.get(gid).session.state
    mike_cards = [c.id for c in state.cards.values() if c.owner == "p2"]
    assert action(client, gid, mike, {"type": "remove_player", "player": "p1"}).status_code == 403
    assert action(client, gid, host, {"type": "remove_player", "player": "p2"}).status_code == 200
    state = client.app.state.services.hub.get(gid).session.state
    assert state.seat_order == ["p1"] and state.players["p2"].left
    assert not any(cid in state.cards for cid in mike_cards)
    assert client.get(f"/api/games/{gid}/view", headers=h(mike)).status_code == 403


def test_return_to_owner_undoes_a_steal(cards):
    s = make_session(cards)
    act(s, "p1", type="draw", count=10)
    sol = find(s.state, "Sol Ring")
    act(s, "p1", type="move", card_ids=[sol.id], to={"zone": "battlefield"})
    act(s, "p2", type="set_controller", card_ids=[sol.id], player="p2")
    assert sol.controller == "p2" and sol.owner == "p1" and sol.zone == "p2:battlefield"
    act(s, "p2", type="move", card_ids=[sol.id], to={"zone": "graveyard"})
    assert sol.zone == "p1:graveyard"  # owner's graveyard, whoever controlled it
    act(s, "p1", type="move", card_ids=[sol.id], to={"zone": "battlefield", "player": "p2"})
    act(s, "p1", type="return_to_owner", card_ids=[sol.id])
    assert sol.zone == "p1:battlefield" and sol.controller == "p1"
    with pytest.raises(ActionError, match="already with their owners"):
        act(s, "p1", type="return_to_owner", card_ids=[sol.id])
    # it survives undo/redo and save/load
    sol = s.state.cards[sol.id]
    s.undo("p1")
    assert s.state.cards[sol.id].controller == "p2"
    s.redo("p1")
    assert s.state.cards[sol.id].controller == "p1"
    assert zone(s.state, "p1", "battlefield") == [sol.id]
