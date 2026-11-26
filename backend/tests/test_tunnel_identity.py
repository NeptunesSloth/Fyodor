"""Who a request on the tunnel port is (app/api/deps.py): the loopback socket only cloudflared connects to. Its requests are never the
host (not by the host cookie, not by a room's host token) and are counted by CF-Connecting-IP, an IPv6 address by its /64."""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.api import deps
from app.netguard import cf_client_key
from tests.conftest import TUNNEL_PORT, connect_game
from tests.test_lobby import create_lobby


def _conn(app: Any, server: Any, headers: dict[str, str] | None = None) -> Request:
    """A bare request as uvicorn would hand it over: ``server`` is the local (address, port) it arrived on."""
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "app": app, "server": server, "client": ("127.0.0.1", 50123), "headers": raw,
                    "method": "GET", "path": "/", "query_string": b"", "scheme": "http"})


def _host_cookie(client: TestClient) -> dict[str, str]:
    secret = client.app.state.services.host_secret.value  # type: ignore[attr-defined]
    return {"Cookie": f"fyodor_host={secret}; __Host-fyodor_host={secret}"}


def _wrong_secret(c: TestClient, **headers: str) -> int:
    return c.post("/api/host/session", json={"secret": "not-it"}, headers=headers).status_code


def test_lan_requests_are_not_tunnel_requests(client, tunnel_client) -> None:
    app = client.app
    assert not deps.is_tunnel_request(_conn(app, ("0.0.0.0", 8000)))  # noqa: S104 - the LAN socket
    assert not deps.is_tunnel_request(_conn(app, ["testserver", 80]))
    assert not deps.is_tunnel_request(_conn(app, None))
    assert not deps.is_tunnel_request(_conn(app, ("127.0.0.1",)))
    assert client.get("/api/host/session").json() == {"host": True}  # the host's browser on the LAN port is still the host
    app.state.services.tunnel.port = None  # a server the launcher didn't start has no tunnel port: nothing is one
    assert not deps.is_tunnel_request(_conn(app, ("127.0.0.1", TUNNEL_PORT)))


def test_a_request_on_the_tunnel_port_is_one(client, tunnel_client) -> None:
    app = client.app
    assert deps.is_tunnel_request(_conn(app, ("127.0.0.1", TUNNEL_PORT)))
    assert deps.is_tunnel_request(_conn(app, ["127.0.0.1", TUNNEL_PORT]))  # (the test client's form)
    assert deps.is_https(_conn(app, ("127.0.0.1", TUNNEL_PORT)))  # the edge serves the visitor only https
    assert not deps.is_https(_conn(app, ("127.0.0.1", 8000)))
    assert "strict-transport-security" in tunnel_client.get("/api/health").headers
    assert "strict-transport-security" not in client.get("/api/health").headers


def test_host_cookie_is_not_host_on_the_tunnel_port(client, tunnel_client) -> None:
    assert client.get("/api/host/session", headers=_host_cookie(client)).json() == {"host": True}
    assert tunnel_client.get("/api/host/session", headers=_host_cookie(client)).json() == {"host": False}


def test_room_host_token_is_not_host_on_the_tunnel_port(client, tunnel_client) -> None:
    gid, code, alice = create_lobby(client)  # Alice is the host's own seat
    client.post("/api/join", json={"code": code, "name": "Bob"}, headers={"Cookie": ""})
    assert client.get(f"/api/games/{gid}/lobby", headers={"X-Seat-Token": alice}).json()["is_host"]  # on the LAN port: the host's
    with connect_game(tunnel_client, gid, alice) as ws:
        first = ws.receive_json()
        assert first["type"] == "lobby" and first["lobby"]["viewer"] == "p1" and first["lobby"]["is_host"] is False
    assert tunnel_client.get(f"/api/games/{gid}/lobby", headers={"X-Seat-Token": alice}).json()["is_host"] is False
    body = {"seat": "p2"}
    assert tunnel_client.post(f"/api/games/{gid}/host/seat-link", json=body, headers={"X-Seat-Token": alice}).status_code == 403
    assert tunnel_client.post(f"/api/games/{gid}/lobby/kick", json=body, headers={"X-Seat-Token": alice}).status_code == 403
    assert client.post(f"/api/games/{gid}/host/seat-link", json=body, headers={"X-Seat-Token": alice}).status_code == 200


def test_tunnel_client_address_is_cf_connecting_ip(client, tunnel_client) -> None:
    services = client.app.state.services
    services.settings = dataclasses.replace(services.settings, trusted_proxies=("127.0.0.1",))  # a proxy that would be believed on the LAN port
    forged = {"X-Forwarded-For": "203.0.113.9"}
    tun = ("127.0.0.1", TUNNEL_PORT)
    assert deps.client_address(_conn(client.app, tun, {"CF-Connecting-IP": "198.51.100.7", **forged})) == "198.51.100.7"
    assert deps.client_address(_conn(client.app, tun, forged)) == "tunnel:unknown"  # no header: the one shared bucket, never the XFF
    assert deps.client_address(_conn(client.app, ("127.0.0.1", 8000), forged)) == "203.0.113.9"  # (the LAN port as before)
    assert _wrong_secret(tunnel_client, **forged) == 403
    assert list(services.host_limiter_addr._failures) == ["198.51.100.7"]


@pytest.mark.parametrize("value,expected", [
    ("198.51.100.7", "198.51.100.7"),
    (" 198.51.100.7 ", "198.51.100.7"),
    ("2001:db8:1:2:aaaa::1", "2001:db8:1:2::/64"),
    ("::ffff:198.51.100.7", "198.51.100.7"),
    (None, "tunnel:unknown"),
    ("", "tunnel:unknown"),
    ("1.2.3.4, 5.6.7.8", "tunnel:unknown"),
    ("x", "tunnel:unknown"),
])
def test_cf_client_key(value, expected) -> None:
    assert cf_client_key(value) == expected


def test_lan_port_never_reads_cf_connecting_ip(client, tunnel_client) -> None:
    services = client.app.state.services
    assert deps.client_address(_conn(client.app, ("127.0.0.1", 8000), {"CF-Connecting-IP": "198.51.100.7"})) == "127.0.0.1"
    assert _wrong_secret(client, **{"CF-Connecting-IP": "198.51.100.7"}) == 403
    assert list(services.host_limiter_addr._failures) == ["testclient"]  # the LAN peer, not the header


def test_two_phones_in_one_ipv6_64_share_a_bucket_but_other_64s_do_not(client, tunnel_client) -> None:
    for _ in range(5):
        assert _wrong_secret(tunnel_client, **{"CF-Connecting-IP": "2001:db8:1:2::aaaa"}) == 403
    assert _wrong_secret(tunnel_client, **{"CF-Connecting-IP": "2001:db8:1:2:ffff::1"}) == 429  # the other phone on that /64
    assert _wrong_secret(tunnel_client, **{"CF-Connecting-IP": "2001:db8:1:3::aaaa"}) == 403  # the next /64 is someone else
    assert _wrong_secret(tunnel_client) == 403  # and so is the IPv4 default


def test_a_seat_reconnects_from_a_new_address(client, tunnel_client) -> None:
    """Review Focus 1: a phone that moves from Wi-Fi to mobile data mid-game keeps its seat (a seat token is never a guess)."""
    from tests.test_protocol_privacy import P1_DECK, P2_DECK

    a = client.post("/api/decks", json={"text": P1_DECK}).json()["id"]
    b = client.post("/api/decks", json={"text": P2_DECK}).json()["id"]
    game = client.post("/api/games", json={
        "mode": "lan", "players": [{"name": "Jonathan", "deck_id": a}, {"name": "Mike", "deck_id": b}],
    }).json()
    gid, code = game["game"]["id"], game["game"]["code"]
    mike = client.post("/api/join", json={"code": code, "name": "Mike"}, headers={"Cookie": ""}).json()["token"]
    services = client.app.state.services
    for address in ("198.51.100.7", "203.0.113.40"):
        with connect_game(tunnel_client, gid, mike, headers={"CF-Connecting-IP": address}) as ws:
            first = ws.receive_json()
            assert first["type"] == "state" and first["view"]["viewer"] == "p2"
    for key in ("198.51.100.7", "203.0.113.40"):
        assert not services.join_limiter_addr.blocked(key) and key not in services.join_limiter_addr._failures
