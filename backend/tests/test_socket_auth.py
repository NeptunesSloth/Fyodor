"""The game socket authenticates in its first message; no token is ever in a URL (game_socket in app/api/games.py)."""

from __future__ import annotations

import dataclasses
import logging
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api import games
from app.config import Settings, load_settings
from app.main import create_app
from tests.conftest import claim_host, connect_game
from tests.test_protocol_privacy import P1_DECK, P2_DECK

LOBBY = {"mode": "lan", "lobby": True, "name": "Friday", "seats": 4, "players": []}


def new_table(client: TestClient) -> tuple[str, str]:
    res = client.post("/api/games", json=LOBBY)
    assert res.status_code == 201, res.text
    body = res.json()
    return body["game"]["id"], body["seat"]["token"]


@pytest.fixture()
def table(client: TestClient) -> tuple[str, str]:
    return new_table(client)


def closed_with(ws) -> WebSocketDisconnect:
    with pytest.raises(WebSocketDisconnect) as raised:
        ws.receive_json()
    return raised.value


def test_auth_message_with_a_seat_token_receives_the_table(client: TestClient, table):
    gid, token = table
    with connect_game(client, gid, token) as ws:
        assert ws.receive_json()["type"] in {"lobby", "state"}


def test_the_connection_remembers_the_token_it_proved(client: TestClient, table):
    gid, token = table
    with connect_game(client, gid, token) as ws:
        ws.receive_json()
        room = client.app.state.services.hub.get(gid)  # type: ignore[attr-defined]
        assert [c.token for c in room.connections.values()] == [token]


def test_nothing_is_sent_and_nobody_is_attached_before_auth(client: TestClient, table, monkeypatch: pytest.MonkeyPatch):
    gid, token = table
    monkeypatch.setattr(games, "AUTH_DEADLINE", 0.5)
    room = client.app.state.services.hub.get(gid)  # type: ignore[attr-defined]
    with client.websocket_connect(f"/ws/games/{gid}") as silent:
        assert room.connections == {}  # accepted, but it counts as nobody
        with connect_game(client, gid, token) as ws:  # another connection makes the room broadcast
            ws.receive_json()
            assert len(room.connections) == 1  # the silent one still is not attached
        err = closed_with(silent)  # the first thing it ever gets is the close: no table, no broadcast
    assert err.code == 4403


def test_wrong_token_closes_4403(client: TestClient, table):
    gid, _ = table
    with connect_game(client, gid, "forged") as ws:
        err = closed_with(ws)
    assert (err.code, err.reason) == (4403, games.AUTH_REFUSED)


def test_missing_token_closes_4403(client: TestClient, table):
    gid, _ = table
    with connect_game(client, gid, None) as ws:  # (even from the host's browser: its cookie is no seat)
        assert closed_with(ws).code == 4403


def test_a_guest_without_a_seat_token_closes_4403(client: TestClient, table):
    gid, _ = table
    with connect_game(client, gid, None, headers={"Cookie": ""}) as ws:
        assert closed_with(ws).code == 4403


def test_first_message_that_is_not_auth_closes_4403(client: TestClient, table):
    gid, token = table
    with client.websocket_connect(f"/ws/games/{gid}") as ws:
        ws.send_json({"type": "action", "action": {"type": "draw"}, "token": token})
        assert closed_with(ws).code == 4403


@pytest.mark.parametrize("payload", [
    "not json at all",
    "[1, 2]",
    "null",
    "\"auth\"",
])
def test_first_message_that_is_not_a_json_object_closes_4403(client: TestClient, table, payload: str):
    gid, _ = table
    with client.websocket_connect(f"/ws/games/{gid}") as ws:
        ws.send_text(payload)
        err = closed_with(ws)
    assert (err.code, err.reason) == (4403, games.AUTH_REFUSED)


def test_oversize_first_message_closes_4403(client: TestClient, table):
    gid, token = table
    with client.websocket_connect(f"/ws/games/{gid}") as ws:
        ws.send_json({"type": "auth", "token": token, "viewer": None, "deltas": False, "pad": "x" * games.MAX_WS_MESSAGE})
        assert closed_with(ws).code == 4403


@pytest.mark.parametrize("fields", [
    {"token": 12345},
    {"token": ["a"]},
    {"token": "t" * 257},
    {"viewer": 5},
    {"deltas": "1"},
    {"deltas": 1},
    {"deltas": None},
])
def test_wrongly_typed_auth_fields_close_4403(client: TestClient, table, fields):
    gid, token = table
    with client.websocket_connect(f"/ws/games/{gid}") as ws:
        ws.send_json({"type": "auth", "token": token, "viewer": None, "deltas": False, **fields})
        assert closed_with(ws).code == 4403


def test_silence_closes_4403_at_the_deadline(client: TestClient, table, monkeypatch: pytest.MonkeyPatch):
    gid, _ = table
    monkeypatch.setattr(games, "AUTH_DEADLINE", 0.05)
    with client.websocket_connect(f"/ws/games/{gid}") as ws:
        err = closed_with(ws)
    assert (err.code, err.reason) == (4403, games.AUTH_REFUSED)


def test_an_unknown_game_closes_exactly_like_a_bad_token(client: TestClient, table):
    gid, token = table
    with connect_game(client, "nonesuch", token) as ws:
        missing = closed_with(ws)
    with connect_game(client, gid, "forged") as ws:
        forged = closed_with(ws)
    assert (missing.code, missing.reason) == (forged.code, forged.reason) == (4403, games.AUTH_REFUSED)


def test_token_in_the_query_alone_is_refused_by_default(client: TestClient, table, monkeypatch: pytest.MonkeyPatch):
    gid, token = table
    monkeypatch.setattr(games, "AUTH_DEADLINE", 0.05)
    with client.websocket_connect(f"/ws/games/{gid}?token={token}") as ws:
        assert closed_with(ws).code == 4403  # nothing came first: not the table, not an error


def test_token_in_the_query_is_honoured_with_the_legacy_switch(settings: Settings, card_db):
    with TestClient(create_app(dataclasses.replace(settings, legacy_ws_token=True))) as c:
        claim_host(c)
        gid, token = new_table(c)
        with c.websocket_connect(f"/ws/games/{gid}?token={token}") as ws:
            assert ws.receive_json()["type"] in {"lobby", "state"}


def test_both_query_token_and_auth_message_are_judged_on_the_auth_message(client: TestClient, table):
    gid, token = table
    with client.websocket_connect(f"/ws/games/{gid}?token={token}") as ws:
        ws.send_json({"type": "auth", "token": "forged", "viewer": None, "deltas": False})
        assert closed_with(ws).code == 4403
    with client.websocket_connect(f"/ws/games/{gid}?token=forged") as ws:
        ws.send_json({"type": "auth", "token": token, "viewer": None, "deltas": False})
        assert ws.receive_json()["type"] in {"lobby", "state"}


def test_the_legacy_switch_is_on_only_for_the_exact_value_1(tmp_path):
    def flag(value: str | None) -> bool:
        env = {"FYODOR_DATA_DIR": str(tmp_path)} | ({"FYODOR_LEGACY_WS_TOKEN": value} if value is not None else {})
        return load_settings(env).legacy_ws_token

    assert [flag(None), flag("1"), flag("true"), flag("yes"), flag("0"), flag("")] == [False, True, False, False, False, False]


def test_no_token_reaches_a_log_line(client: TestClient, table, caplog: pytest.LogCaptureFixture):
    gid, token = table
    caplog.set_level(logging.DEBUG)
    with client.websocket_connect(f"/ws/games/{gid}") as ws:
        assert urlsplit(ws.scope["path"]).query == "" and not ws.scope["query_string"]  # nothing in the upgrade request's address
        ws.send_json({"type": "auth", "token": token, "viewer": None, "deltas": False})
        ws.receive_json()
    with connect_game(client, gid, "forged-secret-value") as ws:
        closed_with(ws)
    assert token not in caplog.text and "forged-secret-value" not in caplog.text


def test_the_seat_link_keeps_the_token_out_of_the_query_string(client: TestClient):
    deck = client.post("/api/decks", json={"text": P1_DECK}).json()["id"]
    other = client.post("/api/decks", json={"text": P2_DECK}).json()["id"]
    game = client.post("/api/games", json={"mode": "lan", "players": [{"name": "Jonathan", "deck_id": deck},
                                                                      {"name": "Mike", "deck_id": other}]}).json()
    gid, host = game["game"]["id"], game["seat"]["token"]
    client.post("/api/join", json={"code": game["game"]["code"], "name": "Mike"})
    link = client.post(f"/api/games/{gid}/host/seat-link", json={"seat": "p2"}, headers={"X-Seat-Token": host}).json()
    parts = urlsplit(link["path"])
    assert parts.query == "" and link["token"] not in parts.path
    assert parts.fragment == f"/game/{gid}?seat_token={link['token']}"  # only after the #, which a browser never sends
