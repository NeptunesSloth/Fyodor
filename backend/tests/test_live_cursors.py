"""Live cursors (as in Tabletop Simulator): seated players' pointers relayed to the rest of the room, never stored."""

from __future__ import annotations

import itertools
from types import SimpleNamespace

import pytest

from app.api.games import WsCursor, _cursor_relay
from tests.test_protocol_privacy import P1_DECK, P2_DECK

_ids = itertools.count(1000)


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
    return client, gid, code, host, mike


def drain(ws) -> list[dict]:
    """Everything this socket received up to now (a ping's pong marks the end), states left out."""
    pid = next(_ids)
    ws.send_json({"type": "ping", "id": pid})
    got = []
    while True:
        msg = ws.receive_json()
        if msg["type"] == "pong" and msg["id"] == pid:
            return [m for m in got if m["type"] not in ("state", "lobby")]
        got.append(msg)


def cursors(msgs: list[dict]) -> list[dict]:
    return [m for m in msgs if m["type"] == "cursor"]


def test_a_cursor_reaches_the_others_but_not_the_sender(table):
    client, gid, _code, host, mike = table
    with client.websocket_connect(f"/ws/games/{gid}?token={host}") as a, client.websocket_connect(f"/ws/games/{gid}?token={mike}") as b:
        drain(a)
        drain(b)
        a.send_json({"type": "cursor", "player": "p2", "x": 512.345, "y": 300})
        assert cursors(drain(a)) == []  # (the pong comes after the relay: the cursor was already sent on)
        assert cursors(drain(b)) == [{"type": "cursor", "from": "p1", "player": "p2", "x": 512.3, "y": 300.0}]
        # off the battlefield (the wood, the rail) is fine, but a wild value is clamped to a sane range
        b.send_json({"type": "cursor", "player": "p1", "x": -99999, "y": 5000})
        drain(b)
        assert cursors(drain(a)) == [{"type": "cursor", "from": "p2", "player": "p1", "x": -400.0, "y": 1000.0}]
        # gone: the pointer left the table
        a.send_json({"type": "cursor", "gone": True})
        drain(a)
        assert cursors(drain(b)) == [{"type": "cursor", "from": "p1", "gone": True}]
        # nonsense is dropped quietly: an unknown seat, missing coordinates, extra fields
        for bad in ({"type": "cursor", "player": "p9", "x": 1, "y": 1}, {"type": "cursor", "player": "p1"},
                    {"type": "cursor", "player": "p1", "x": 1, "y": 1, "hand": "secret"}):
            a.send_json(bad)
        assert cursors(drain(a)) == []
        assert cursors(drain(b)) == []


def test_a_cursor_names_only_a_card_everyone_can_see(table):
    client, gid, _code, host, mike = table
    client.post(f"/api/games/{gid}/actions", json={"action": {"type": "draw", "count": 3}}, headers={"X-Seat-Token": host})
    state = client.app.state.services.hub.get(gid).session.state
    hand = state.zones["p1:hand"][0]
    library = state.zones["p1:library"][0]
    commander = state.zones["p1:command"][0]
    with client.websocket_connect(f"/ws/games/{gid}?token={host}") as a, client.websocket_connect(f"/ws/games/{gid}?token={mike}") as b:
        drain(a)
        drain(b)
        a.send_json({"type": "cursor", "player": "p1", "x": 10, "y": 20, "card": commander, "cx": 0.25, "cy": -3})
        for hidden in (hand, library):  # my hand and my library: the spot goes, the id never does
            a.send_json({"type": "cursor", "player": "p1", "x": 11, "y": 20, "card": hidden, "cx": 0.1, "cy": 0.1})
        drain(a)
        got = cursors(drain(b))
        assert got[0] == {"type": "cursor", "from": "p1", "player": "p1", "x": 10.0, "y": 20.0, "card": commander, "cx": 0.25, "cy": -1.0}
        assert got[1:] == [{"type": "cursor", "from": "p1", "player": "p1", "x": 11.0, "y": 20.0}] * 2


def test_cursors_are_never_stored_or_logged(table):
    client, gid, _code, host, mike = table
    room = client.app.state.services.hub.get(gid)
    before = (room.session.state.seq, len(room.session.state.log))
    with client.websocket_connect(f"/ws/games/{gid}?token={host}") as a:
        drain(a)
        for i in range(10):
            a.send_json({"type": "cursor", "player": "p1", "x": i, "y": i})
        drain(a)
    assert (room.session.state.seq, len(room.session.state.log)) == before


def test_excess_cursors_are_dropped_without_errors(table):
    client, gid, _code, host, mike = table
    with client.websocket_connect(f"/ws/games/{gid}?token={host}") as a, client.websocket_connect(f"/ws/games/{gid}?token={mike}") as b:
        drain(a)
        drain(b)
        for i in range(60):
            a.send_json({"type": "cursor", "player": "p1", "x": i, "y": 0})
        mine = drain(a)
        assert [m for m in mine if m["type"] == "error"] == []
        got = cursors(drain(b))
        assert 20 <= len(got) < 30  # the burst, and what refilled while they arrived
        # actions keep their own budget: moving the mouse never slows a player down
        a.send_json({"type": "action", "action": {"type": "draw"}, "id": 7})
        answer = a.receive_json()
        while answer["type"] not in ("ack", "error"):
            answer = a.receive_json()
        assert answer == {"type": "ack", "id": 7, "status": "ACCEPTED"}


def test_spectators_see_cursors_but_cannot_send_them(table):
    client, gid, code, host, mike = table
    spectator = client.post("/api/join", json={"code": code, "spectate": True}).json()["token"]
    with client.websocket_connect(f"/ws/games/{gid}?token={host}") as a, client.websocket_connect(f"/ws/games/{gid}?token={spectator}") as s:
        drain(a)
        drain(s)
        s.send_json({"type": "cursor", "player": "p1", "x": 10, "y": 10})
        s.send_json({"type": "cursor", "gone": True})
        assert [m for m in drain(s) if m["type"] in ("cursor", "error")] == []
        assert cursors(drain(a)) == []
        a.send_json({"type": "cursor", "player": "p1", "x": 10, "y": 20})
        drain(a)
        assert cursors(drain(s)) == [{"type": "cursor", "from": "p1", "player": "p1", "x": 10.0, "y": 20.0}]


def test_leaving_the_table_takes_the_cursor_away(table):
    client, gid, _code, host, mike = table
    with client.websocket_connect(f"/ws/games/{gid}?token={mike}") as b:
        drain(b)
        with client.websocket_connect(f"/ws/games/{gid}?token={host}") as a:
            drain(a)
            a.send_json({"type": "cursor", "player": "p1", "x": 1, "y": 2})
            drain(a)
            assert cursors(drain(b))[0]["from"] == "p1"
        msg = b.receive_json()
        while msg["type"] != "cursor":
            msg = b.receive_json()
        assert msg == {"type": "cursor", "from": "p1", "gone": True}


def test_hot_seat_tables_and_lobbies_relay_nothing():
    msg = WsCursor(type="cursor", player="p1", x=1, y=1)
    conn = SimpleNamespace(actor="p1")
    local = SimpleNamespace(mode="local", started=True)
    lobby = SimpleNamespace(mode="lan", started=False)
    assert _cursor_relay(local, conn, msg) is None  # type: ignore[arg-type]
    assert _cursor_relay(lobby, conn, msg) is None  # type: ignore[arg-type]
