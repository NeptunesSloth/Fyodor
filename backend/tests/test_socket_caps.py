"""Game socket caps (per seat, per address), the heartbeat, and closing the sockets of a seat that was replaced or taken away."""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api import games
from app.multiplayer.hub import Room
from app.netguard import ConnectionCaps
from tests.conftest import connect_game

LOBBY = {"mode": "lan", "lobby": True, "name": "Friday", "seats": 4, "players": [{"name": "Alice"}]}


def h(token: str) -> dict[str, str]:
    return {"X-Seat-Token": token}


@pytest.fixture()
def table(client: TestClient) -> tuple[str, str, str]:
    """(game id, room code, host token) of a lobby with the host in seat p1."""
    body = client.post("/api/games", json=LOBBY).json()
    return body["game"]["id"], body["game"]["code"], body["seat"]["token"]


def join(client: TestClient, code: str, name: str) -> str:
    res = client.post("/api/join", json={"code": code, "name": name})
    assert res.status_code in (200, 201), res.text
    return res.json()["token"]


def services(client: TestClient):
    return client.app.state.services  # type: ignore[attr-defined]


def room_of(client: TestClient, gid: str) -> Room:
    room = services(client).hub.get(gid)
    assert room is not None
    return room


def seat_of(client: TestClient, gid: str, token: str) -> str:
    seat = room_of(client, gid).seat_for_token(token)
    assert seat is not None
    return seat


def wait_until(check: Callable[[], bool], what: str, limit: float = 3.0) -> None:
    """The server side of a closed socket finishes on its own thread: poll for it rather than sleep a guess."""
    end = time.monotonic() + limit
    while not check():
        assert time.monotonic() < end, f"never happened: {what}"
        time.sleep(0.01)


def closed_with(ws) -> WebSocketDisconnect:
    """Read until the server closes this socket (updates in between are ignored)."""
    while True:
        try:
            ws.receive_json()
        except WebSocketDisconnect as gone:
            return gone


def alive(ws) -> bool:
    """Is this socket still being served? A ping gets its pong (other updates may come first)."""
    ws.send_json({"type": "ping", "id": 7})
    while True:
        msg = ws.receive_json()
        if msg["type"] == "pong" and msg.get("id") == 7:
            return True


# --------------------------------------------------------------------------- the counter itself


def test_caps_count_per_key_and_refuse_over_the_limit():
    caps = ConnectionCaps(2)
    assert [caps.acquire("a"), caps.acquire("a"), caps.acquire("a"), caps.acquire("b")] == [True, True, False, True]
    caps.release("a")
    assert caps.acquire("a") is True
    assert caps.acquire("a") is False


def test_a_release_without_an_acquire_never_goes_negative_or_frees_a_slot():
    caps = ConnectionCaps(1)
    caps.release("nobody")  # nothing was held
    assert caps.total() == 0
    assert caps.acquire("a") is True
    caps.release("b")  # someone else's key
    assert caps.acquire("a") is False
    caps.release("a")
    caps.release("a")  # one too many
    assert caps.total() == 0
    assert [caps.acquire("a"), caps.acquire("a")] == [True, False]  # still exactly one slot


def test_services_carry_the_documented_caps(client: TestClient):
    s = services(client)
    assert (s.caps_seat.per_key, s.caps_addr.per_key) == (4, 24)


# --------------------------------------------------------------------------- per seat


def test_a_fifth_socket_for_one_seat_closes_4429_and_the_first_four_stay(client: TestClient, table):
    gid, _, host = table
    with contextlib.ExitStack() as stack:
        four = [stack.enter_context(connect_game(client, gid, host)) for _ in range(4)]
        for ws in four:
            assert ws.receive_json()["type"] in {"lobby", "state"}
        with connect_game(client, gid, host) as fifth:
            gone = closed_with(fifth)
        assert (gone.code, gone.reason) == (4429, "Too many connections")
        assert all(alive(ws) for ws in four)
        assert services(client).caps_seat.count(f"{gid}:p1") == 4  # the refused one released nothing of theirs


def test_closing_one_lets_a_new_one_in(client: TestClient, table):
    gid, _, host = table
    caps = services(client).caps_seat
    with contextlib.ExitStack() as stack:
        four = [stack.enter_context(connect_game(client, gid, host)) for _ in range(4)]
        for ws in four:
            ws.receive_json()
        stack.close()  # (all four close; one at a time below is the same path)
    wait_until(lambda: caps.count(f"{gid}:p1") == 0, "the four slots are free")
    with connect_game(client, gid, host) as ws:
        assert ws.receive_json()["type"] in {"lobby", "state"}


def test_one_seat_full_does_not_stop_another_seat(client: TestClient, table):
    gid, code, host = table
    bob = join(client, code, "Bob")
    with contextlib.ExitStack() as stack:
        for _ in range(4):
            stack.enter_context(connect_game(client, gid, host))
        with connect_game(client, gid, bob) as ws:
            assert ws.receive_json()["type"] in {"lobby", "state"}


def test_a_spectator_takes_only_the_address_cap(client: TestClient, table):
    gid, code, _ = table
    spectator = client.post("/api/join", json={"code": code, "spectate": True}).json()["token"]
    s = services(client)
    with contextlib.ExitStack() as stack:
        socks = [stack.enter_context(connect_game(client, gid, spectator)) for _ in range(5)]
        for ws in socks:
            assert ws.receive_json()["type"] in {"lobby", "state"}
        assert s.caps_seat.total() == 0
        assert s.caps_addr.total() == 5


# --------------------------------------------------------------------------- per address


def test_the_25th_unauthenticated_socket_from_one_address_is_refused_before_accept(client: TestClient, table, monkeypatch):
    gid, _, _ = table
    monkeypatch.setattr(games, "AUTH_DEADLINE", 30.0)  # (they all stay silent)
    with contextlib.ExitStack() as stack:
        for _ in range(24):
            stack.enter_context(client.websocket_connect(f"/ws/games/{gid}"))
        with pytest.raises(WebSocketDisconnect) as refused, client.websocket_connect(f"/ws/games/{gid}"):
            pass
        assert refused.value.code == 4429  # (never accepted: the handshake itself failed)
        assert services(client).caps_addr.total() == 24
    wait_until(lambda: services(client).caps_addr.total() == 0, "all 24 released")


# --------------------------------------------------------------------------- released on every path


def test_the_caps_are_released_after_a_normal_close(client: TestClient, table):
    gid, _, host = table
    s = services(client)
    with connect_game(client, gid, host) as ws:
        ws.receive_json()
        assert (s.caps_seat.total(), s.caps_addr.total()) == (1, 1)
    wait_until(lambda: (s.caps_seat.total(), s.caps_addr.total()) == (0, 0), "both released")


def test_the_address_cap_is_released_after_refused_auth_and_after_the_deadline(client: TestClient, table, monkeypatch):
    gid, _, _ = table
    s = services(client)
    with connect_game(client, gid, "forged") as ws:
        assert closed_with(ws).code == 4403
    wait_until(lambda: s.caps_addr.total() == 0, "refused auth released")
    monkeypatch.setattr(games, "AUTH_DEADLINE", 0.05)
    with client.websocket_connect(f"/ws/games/{gid}") as ws:
        assert closed_with(ws).code == 4403
    wait_until(lambda: s.caps_addr.total() == 0, "deadline released")
    assert s.caps_seat.total() == 0


def test_the_caps_are_released_when_serving_the_socket_raises(client: TestClient, table, monkeypatch):
    gid, _, host = table
    s = services(client)

    def broken(conn, message):
        raise RuntimeError("boom")

    monkeypatch.setattr(s.hub, "full", broken)
    with pytest.raises(RuntimeError, match="boom"), connect_game(client, gid, host) as ws:
        ws.receive_json()
    wait_until(lambda: (s.caps_seat.total(), s.caps_addr.total()) == (0, 0), "released after the error")


def test_a_dropped_socket_frees_its_slot(client: TestClient, table, monkeypatch):
    """The phone that slept: no close frame ever comes, only silence; the idle close frees the slot."""
    gid, _, host = table
    s = services(client)
    monkeypatch.setattr(games, "PING_EVERY", 0.05)
    monkeypatch.setattr(games, "IDLE_CLOSE", 0.3)
    with connect_game(client, gid, host) as ws:
        assert closed_with(ws).code == 4408
        wait_until(lambda: (s.caps_seat.total(), s.caps_addr.total()) == (0, 0), "released by the idle close")
        assert room_of(client, gid).seats["p1"].connections == 0


# --------------------------------------------------------------------------- heartbeat


def test_the_server_pings_with_nothing_else_in_the_message(client: TestClient, table, monkeypatch):
    gid, _, host = table
    monkeypatch.setattr(games, "PING_EVERY", 0.05)
    monkeypatch.setattr(games, "IDLE_CLOSE", 5.0)
    with connect_game(client, gid, host) as ws:
        ws.receive_json()
        while (msg := ws.receive_json())["type"] != "ping":
            pass
        assert msg == {"type": "ping"}


def test_a_silent_connection_is_closed_4408(client: TestClient, table, monkeypatch):
    gid, _, host = table
    monkeypatch.setattr(games, "PING_EVERY", 0.05)
    monkeypatch.setattr(games, "IDLE_CLOSE", 0.3)
    with connect_game(client, gid, host) as ws:
        assert closed_with(ws).code == 4408


def test_a_connection_that_answers_pings_stays_open_past_the_idle_limit(client: TestClient, table, monkeypatch):
    gid, _, host = table
    monkeypatch.setattr(games, "PING_EVERY", 0.1)
    monkeypatch.setattr(games, "IDLE_CLOSE", 1.0)
    with connect_game(client, gid, host) as ws:
        start, pings = time.monotonic(), 0
        while time.monotonic() - start < 1.6:  # longer than IDLE_CLOSE
            if ws.receive_json()["type"] == "ping":
                pings += 1
                ws.send_json({"type": "pong"})
        assert pings >= 3
        assert alive(ws)


def test_any_message_counts_as_activity(client: TestClient, table, monkeypatch):
    gid, _, host = table
    monkeypatch.setattr(games, "PING_EVERY", 5.0)
    monkeypatch.setattr(games, "IDLE_CLOSE", 1.0)
    with connect_game(client, gid, host) as ws:
        start = time.monotonic()
        while time.monotonic() - start < 1.6:
            ws.send_json({"type": "ping", "id": 7})  # (the page's own keepalive)
            while ws.receive_json()["type"] != "pong":
                pass
            time.sleep(0.2)
        assert alive(ws)


def test_pongs_are_not_errors_and_never_count_against_the_rate_limit(client: TestClient, table, monkeypatch):
    gid, _, host = table
    monkeypatch.setattr(games, "PING_EVERY", 60.0)
    with connect_game(client, gid, host) as ws:
        ws.receive_json()
        for _ in range(200):  # far more than the limiter's burst
            ws.send_json({"type": "pong"})
        ws.send_json({"type": "ping", "id": 9})
        seen = []
        while (msg := ws.receive_json())["type"] != "pong":
            seen.append(msg)
        assert not [m for m in seen if m["type"] == "error"]  # no "Malformed message", no "Slow down"


# --------------------------------------------------------------------------- a replaced seat


def test_after_a_reclaim_the_old_tokens_sockets_close_4403_and_only_those(client: TestClient, table):
    gid, code, host = table
    bob, carol = join(client, code, "Bob"), join(client, code, "Carol")
    seat = seat_of(client, gid, bob)
    with connect_game(client, gid, bob) as old1, connect_game(client, gid, bob) as old2, \
            connect_game(client, gid, carol) as other, connect_game(client, gid, host) as hosts:
        for ws in (old1, old2, other, hosts):
            ws.receive_json()
        link = client.post(f"/api/games/{gid}/host/seat-link", json={"seat": seat}, headers=h(host)).json()
        assert closed_with(old1).code == 4403
        assert closed_with(old2).code == 4403
        assert alive(other) and alive(hosts)  # nobody else's connection was touched
        with connect_game(client, gid, bob) as stale:  # the old token no longer gets in
            assert closed_with(stale).code == 4403
        with connect_game(client, gid, link["token"]) as fresh:  # the new one does
            assert fresh.receive_json()["type"] in {"lobby", "state"}
    wait_until(lambda: services(client).caps_seat.count(f"{gid}:{seat}") == 0, "the replaced seat's slots are free")


def test_a_kicked_player_s_sockets_close_4403(client: TestClient, table):
    gid, code, host = table
    bob = join(client, code, "Bob")
    seat = seat_of(client, gid, bob)
    with connect_game(client, gid, bob) as kicked, connect_game(client, gid, host) as hosts:
        kicked.receive_json()
        hosts.receive_json()
        assert client.post(f"/api/games/{gid}/lobby/kick", json={"seat": seat}, headers=h(host)).status_code == 200
        assert closed_with(kicked).code == 4403
        assert alive(hosts)
        with connect_game(client, gid, bob) as again:
            assert closed_with(again).code == 4403


def test_a_player_who_leaves_the_lobby_has_their_sockets_closed_4403(client: TestClient, table):
    gid, code, _ = table
    bob = join(client, code, "Bob")
    with connect_game(client, gid, bob) as ws:
        ws.receive_json()
        assert client.post(f"/api/games/{gid}/lobby/leave", headers=h(bob)).status_code == 204
        assert closed_with(ws).code == 4403


def test_close_seat_connections_closes_only_that_seat(client: TestClient, table):
    gid, code, host = table
    bob = join(client, code, "Bob")
    seat = seat_of(client, gid, bob)
    room = room_of(client, gid)
    with connect_game(client, gid, bob) as mine, connect_game(client, gid, host) as hosts:
        mine.receive_json()
        hosts.receive_json()
        client.portal.call(services(client).hub.close_seat_connections, room, seat, "test")  # type: ignore[attr-defined]
        assert closed_with(mine).code == 4403
        assert alive(hosts)

