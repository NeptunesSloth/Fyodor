"""At most MAX_SPECTATORS spectator tokens per room: the earliest is let go (token dead, sockets closed 4403, queued deck dropped)."""

from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect

from app.multiplayer.hub import MAX_SPECTATORS
from tests.conftest import connect_game
from tests.test_protocol_privacy import P1_DECK, P2_DECK


@pytest.fixture()
def table(client):
    a = client.post("/api/decks", json={"text": P1_DECK}).json()["id"]
    b = client.post("/api/decks", json={"text": P2_DECK}).json()["id"]
    game = client.post("/api/games", json={
        "mode": "lan", "players": [{"name": "Jonathan", "deck_id": a}, {"name": "Mike", "deck_id": b}],
    }).json()
    gid, code = game["game"]["id"], game["game"]["code"]
    return client, gid, code, game["seat"]["token"]


def watch(client, code):
    res = client.post("/api/join", json={"code": code, "spectate": True})
    assert res.status_code == 200, res.text
    return res.json()["token"]


def status(client, gid, token):
    return client.get(f"/api/games/{gid}/view", headers={"X-Seat-Token": token}).status_code


def room_of(client, gid):
    return client.app.state.services.hub.rooms[gid]


def test_33_spectators_leave_32_and_the_first_is_refused(table):
    client, gid, code, _ = table
    tokens = [watch(client, code) for _ in range(MAX_SPECTATORS + 1)]
    assert MAX_SPECTATORS == 32
    assert room_of(client, gid).spectator_tokens == tokens[1:]
    assert status(client, gid, tokens[0]) == 403
    assert status(client, gid, tokens[1]) == 200 and status(client, gid, tokens[-1]) == 200


def test_the_dropped_spectators_socket_closes_4403(table):
    client, gid, code, _ = table
    first = watch(client, code)
    with connect_game(client, gid, first) as ws:
        ws.receive_json()
        for _ in range(MAX_SPECTATORS):
            watch(client, code)
        with pytest.raises(WebSocketDisconnect) as info:
            for _ in range(10):
                ws.receive_json()
        assert info.value.code == 4403
        assert info.value.reason == "Too many spectators: the earliest one was let go."
    assert room_of(client, gid).dropped_spectators == []


def test_a_dropped_spectators_queued_deck_goes_with_them(table):
    client, gid, code, _ = table
    room = room_of(client, gid)
    first = watch(client, code)
    room.night.queued[first] = object()  # type: ignore[assignment]
    keeper = watch(client, code)
    room.night.queued[keeper] = object()  # type: ignore[assignment]
    for _ in range(MAX_SPECTATORS - 1):
        watch(client, code)
    assert first not in room.spectator_tokens and first not in room.night.queued and keeper in room.night.queued


def test_restore_keeps_the_newest_32_of_40_in_order_and_round_trips(table):
    client, gid, _, _ = table
    hub = client.app.state.services.hub
    room = room_of(client, gid)
    meta = hub.meta(room)
    names = [f"t{i:02d}" for i in range(40)]
    for listing in (names, sorted(names, reverse=True)[::-1], set(names)):
        meta["spectator_tokens"] = list(listing)
        restored = hub.restore(meta, room.session, {})
        assert len(restored.spectator_tokens) == MAX_SPECTATORS
        assert restored.spectator_tokens == list(listing)[-MAX_SPECTATORS:]
    meta["spectator_tokens"] = names
    restored = hub.restore(meta, room.session, {})
    again = hub.restore(hub.meta(restored), restored.session, {})
    assert again.spectator_tokens == names[-MAX_SPECTATORS:] == hub.meta(restored)["spectator_tokens"]


def test_the_cap_leaves_seats_alone(table):
    client, gid, code, host = table
    mike = client.post("/api/join", json={"code": code, "name": "Mike"}).json()["token"]
    for _ in range(MAX_SPECTATORS + 5):
        watch(client, code)
    assert status(client, gid, host) == 200 and status(client, gid, mike) == 200
    assert {s.token for s in room_of(client, gid).seats.values()} >= {host, mike}
