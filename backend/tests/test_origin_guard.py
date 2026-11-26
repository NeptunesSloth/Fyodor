"""Cross-site requests and DNS rebinding: an allowed Origin on sockets and state-changing requests, an allowed Host on everything
(app/netguard.py, the middleware in app/main.py, game_socket in app/api/games.py)."""

from __future__ import annotations

import contextlib
import dataclasses
import socket
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import netguard
from app.config import Settings, load_settings
from app.main import create_app
from tests.conftest import claim_host, connect_game

LOBBY = {"mode": "lan", "lobby": True, "name": "Friday", "seats": 4, "players": []}
OWN = "http://testserver"


@pytest.fixture()
def lan_game(client: TestClient) -> tuple[str, str]:
    res = client.post("/api/games", json=LOBBY)
    assert res.status_code == 201, res.text
    body = res.json()
    return body["game"]["id"], body["seat"]["token"]


def games(client: TestClient) -> list[dict]:
    return client.get("/api/games").json()


# ----------------------------------------------------------------------------------------------------- the functions


@pytest.mark.parametrize("origin,host,expected", [
    ("http://192.168.1.20:8000", "192.168.1.20:8000", True),
    ("http://127.0.0.1:8000", "127.0.0.1:8000", True),
    ("https://play.example.org", "play.example.org", True),               # a tunnel: https, default port on both sides
    ("http://play.example.org:80", "play.example.org", True),             # default port written out
    ("https://play.example.org:443", "play.example.org", True),
    ("HTTP://Play.Example.org", "play.example.ORG", True),                # case-insensitive
    ("http://[::1]:8000", "[::1]:8000", True),
    ("http://192.168.1.20:8000.evil.example", "192.168.1.20:8000", False),  # never a prefix match
    ("http://192.168.1.20:8000.evil.example", "192.168.1.20:8000.evil.example", False),
    ("http://192.168.1.20.evil.example:8000", "192.168.1.20:8000", False),
    ("http://evil.example", "192.168.1.20:8000", False),
    ("http://192.168.1.20:9000", "192.168.1.20:8000", False),             # another port is another origin
    ("http://192.168.1.20:8000/path", "192.168.1.20:8000", False),        # an Origin has no path
    ("http://user@192.168.1.20:8000", "192.168.1.20:8000", False),
    ("http://127.0.0.1:8000#", "127.0.0.1:8000", False),                  # not a serialized origin: empty fragment, empty query,
    ("http://127.0.0.1:8000?", "127.0.0.1:8000", False),                  # empty port, leading zeros, whitespace, control characters
    ("http://testserver:", "testserver", False),
    ("http://127.0.0.1:08000", "127.0.0.1:8000", False),
    (" http://testserver", "testserver", False),
    ("http://testserver ", "testserver", False),
    ("http://test\tserver", "testserver", False),
    ("http://testserver\n", "testserver", False),
    ("http://testserver/", "testserver", False),
    ("http://testserver:99999", "testserver", False),
    ("http://[::1]:", "[::1]", False),
    ("http://Kevin", "kevin", False),                                  # the Kelvin sign is not folded into an ASCII k
    ("http://kıvin", "kivin", False),                                  # nor is a dotless i
    ("http://[::1", "[::1]", False),
    ("null", "192.168.1.20:8000", False),
    ("ftp://192.168.1.20:8000", "192.168.1.20:8000", False),
    ("", "192.168.1.20:8000", False),
    (None, "192.168.1.20:8000", False),
    ("http://192.168.1.20:8000", None, False),
    ("http://192.168.1.20:8000", "", False),
])
def test_origin_allowed(origin, host, expected):
    assert netguard.origin_allowed(origin, host, ()) is expected


def test_origin_allowed_by_the_extra_list():
    extra = ["http://localhost:5173", "https://Invite.Example.org"]
    assert netguard.origin_allowed("http://localhost:5173", "192.168.1.20:8000", extra)
    assert netguard.origin_allowed("https://invite.example.org", "192.168.1.20:8000", extra)
    assert not netguard.origin_allowed("http://localhost:5173.evil.example", "192.168.1.20:8000", extra)
    assert not netguard.origin_allowed("http://localhost:5174", "192.168.1.20:8000", extra)
    assert not netguard.origin_allowed(None, "192.168.1.20:8000", extra)


@pytest.mark.parametrize("host,expected", [
    ("192.168.1.20:8000", True),
    ("192.168.1.20", True),
    ("127.0.0.1:8000", True),
    ("[::1]:8000", True),
    ("[::1]", True),
    ("[fe80::1]:8000", True),
    ("localhost", True),
    ("LocalHost:8000", True),
    ("evil.example", False),
    ("evil.example:8000", False),
    ("localhost.evil.example", False),
    ("::1", False),                                   # an IPv6 literal in a Host header is bracketed
    ("192.168.1.20:80x", False),
    ("192.168.1.20:", False),
    ("[::1]:", False),
    ("[fe80::1%a;b]:8000", False),                    # a zone id ('%') is never part of a Host: ipaddress takes any text after it
    ("[fe80::1%a b]", False),
    ("[fe80::1%eth0]", False),
    ("[fe80::1%25eth0]:8000", False),
    ("", False),
    (None, False),
])
def test_host_allowed_literals_and_localhost(host, expected):
    assert netguard.host_allowed(host, ()) is expected


def test_host_allowed_machine_name():
    name = socket.gethostname()
    for host in (name, name.upper(), f"{name}:8000", f"{name}.local", f"{name.upper()}.LOCAL:8000"):
        assert netguard.host_allowed(host, ()), host
    for host in (f"{name}.evil.example", f"evil{name}", f"{name}.local.evil.example", f"x.{name}"):
        assert not netguard.host_allowed(host, ()), host


def test_host_allowed_extra_hosts():
    assert netguard.host_allowed("invite.example.org", ("invite.example.org",))
    assert netguard.host_allowed("Invite.Example.org:443", ("invite.example.org",))
    assert not netguard.host_allowed("invite.example.org", ())
    assert not netguard.host_allowed("evil.invite.example.org", ("invite.example.org",))


def test_settings_extra_hosts(tmp_path):
    base = {"FYODOR_DATA_DIR": str(tmp_path)}
    assert load_settings({**base, "FYODOR_EXTRA_HOSTS": ""}).extra_hosts == ()
    assert load_settings({**base, "FYODOR_EXTRA_HOSTS": " "}).extra_hosts == ()
    assert load_settings({**base, "FYODOR_EXTRA_HOSTS": "Play.Example.org, other.example"}).extra_hosts == ("play.example.org", "other.example")
    # empty entries (a trailing comma, two in a row) are skipped, as FYODOR_TRUSTED_PROXIES skips them
    assert load_settings({**base, "FYODOR_EXTRA_HOSTS": "play.example.org,, other.example ,"}).extra_hosts == ("play.example.org", "other.example")
    assert load_settings({**base, "FYODOR_EXTRA_HOSTS": ","}).extra_hosts == ()


# ----------------------------------------------------------------------------------------------- state-changing requests


def test_same_origin_post_passes(client: TestClient):
    res = client.post("/api/games", json=LOBBY, headers={"Origin": OWN, "Sec-Fetch-Site": "same-origin"})
    assert res.status_code == 201


def test_a_foreign_origin_post_is_refused_and_changes_nothing(client: TestClient):
    before = games(client)
    for method in ("post", "put", "patch", "delete"):
        res = getattr(client, method)("/api/games", headers={"Origin": "https://evil.example"})
        assert res.status_code == 403 and res.json() == {"detail": "Cross-site request refused"}, method
    res = client.post("/api/games", json=LOBBY, headers={"Origin": "https://evil.example"})
    assert res.status_code == 403 and res.json() == {"detail": "Cross-site request refused"}
    assert games(client) == before


def test_a_prefix_lookalike_origin_is_refused(client: TestClient):
    res = client.post("/api/games", json=LOBBY, headers={"Origin": "http://testserver.evil.example"})
    assert res.status_code == 403


def test_origin_null_is_refused(client: TestClient):
    assert client.post("/api/games", json=LOBBY, headers={"Origin": "null"}).status_code == 403


def test_cross_site_fetch_metadata_is_refused_even_without_an_origin(client: TestClient):
    before = games(client)
    assert client.post("/api/games", json=LOBBY, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.post("/api/games", json=LOBBY, headers={"Sec-Fetch-Site": "cross-site", "Origin": OWN}).status_code == 403
    assert games(client) == before


def test_same_site_is_decided_by_the_origin(client: TestClient):
    assert client.post("/api/games", json=LOBBY, headers={"Sec-Fetch-Site": "same-site"}).status_code == 403  # a browser sent it, no Origin
    assert client.post("/api/games", json=LOBBY, headers={"Sec-Fetch-Site": "same-site", "Origin": "http://other.testserver"}).status_code == 403
    assert client.post("/api/games", json=LOBBY, headers={"Sec-Fetch-Site": "same-site", "Origin": OWN}).status_code == 201


def test_a_typed_navigation_passes(client: TestClient):
    assert client.post("/api/games", json=LOBBY, headers={"Sec-Fetch-Site": "none"}).status_code == 201


def test_no_origin_and_no_fetch_metadata_passes(client: TestClient):
    # not a browser: the Fyodor-to-Fyodor handoff (app/api/lan.py), bots, scripts
    assert client.post("/api/games", json=LOBBY).status_code == 201


def test_a_get_with_a_foreign_origin_still_works(client: TestClient):
    assert client.get("/api/health", headers={"Origin": "https://evil.example"}).status_code == 200
    assert client.get("/api/health", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200


DEV = "http://localhost:5173"


@contextlib.contextmanager
def served(tmp_path, env: dict[str, str]) -> Iterator[TestClient]:
    base = {"FYODOR_DATA_DIR": str(tmp_path / "data"), "FYODOR_FRONTEND_DIST": str(tmp_path / "nodist")}
    with TestClient(create_app(load_settings(base | env))) as c:
        yield claim_host(c)


def test_dev_origins_are_refused_by_default(client: TestClient):
    assert client.app.state.services.settings.cors_origins == ()  # type: ignore[attr-defined]
    assert client.post("/api/games", json=LOBBY, headers={"Origin": DEV}).status_code == 403
    assert client.post("/api/games", json=LOBBY, headers={"Origin": "http://127.0.0.1:5173"}).status_code == 403


def test_dev_origins_with_dev_tools(tmp_path):
    with served(tmp_path, {"FYODOR_DEV_TOOLS": "1"}) as c:
        assert c.post("/api/games", json=LOBBY, headers={"Origin": DEV}).status_code == 201
        assert c.post("/api/games", json=LOBBY, headers={"Origin": "http://127.0.0.1:5173"}).status_code == 201
        assert c.post("/api/games", json=LOBBY, headers={"Origin": "http://localhost:5174"}).status_code == 403


def test_cors_origins_variable_wins(tmp_path):
    for env in ({"FYODOR_CORS_ORIGINS": "https://a.example"}, {"FYODOR_CORS_ORIGINS": "https://a.example", "FYODOR_DEV_TOOLS": "1"}):
        with served(tmp_path, env) as c:
            assert c.post("/api/games", json=LOBBY, headers={"Origin": "https://a.example"}).status_code == 201
            assert c.post("/api/games", json=LOBBY, headers={"Origin": DEV}).status_code == 403


def test_an_invite_origin_in_services_extra_origins_passes(client: TestClient):
    assert client.app.state.services.extra_origins == set()  # type: ignore[attr-defined]
    headers = {"Origin": "https://invite.example.org"}
    assert client.post("/api/games", json=LOBBY, headers=headers).status_code == 403
    client.app.state.services.extra_origins.add("https://invite.example.org")  # type: ignore[attr-defined]
    assert client.post("/api/games", json=LOBBY, headers=headers).status_code == 201


# ------------------------------------------------------------------------------------------------------- the Host header


FQDN = "desktop-42.lan"  # the name a home router hands out (socket.getfqdn), stood in for this computer's


@pytest.fixture()
def router_named(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getfqdn", lambda name="": FQDN.upper())
    monkeypatch.setattr(netguard, "OWN_NAMES", netguard.own_names())  # (worked out once at start)


@pytest.mark.parametrize("host", ["192.168.1.20:8000", "localhost:8000", "127.0.0.1:8000", "[::1]:8000", socket.gethostname(),
                                  socket.gethostname().upper() + ":8000", socket.gethostname() + ".local", FQDN + ":8000", FQDN])
def test_these_hosts_are_served(client: TestClient, host: str, router_named: None):
    assert client.get("/api/health", headers={"Host": host}).status_code == 200


def test_the_router_assigned_name_is_this_computers(router_named: None):
    assert netguard.host_allowed("Desktop-42.LAN:8000", ())
    assert not netguard.host_allowed(f"x.{FQDN}", ()) and not netguard.host_allowed(f"{FQDN}.evil.example", ())


def test_a_foreign_host_is_refused_even_for_a_get(client: TestClient):
    res = client.get("/api/health", headers={"Host": "evil.example"})
    assert res.status_code == 400
    # a person who typed a name into the address bar reads why, and what to do
    assert res.headers["content-type"].startswith("text/plain")
    assert res.text == ("This address is not one Fyodor answers to. Use http://<IP>:<port>, or add the name to "
                        "FYODOR_EXTRA_HOSTS.")
    assert client.get("/", headers={"Host": "evil.example:8000"}).status_code == 400
    assert client.get("/assets/x.js", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/api/health", headers={"Host": f"{socket.gethostname()}.evil.example"}).status_code == 400


def test_the_host_is_checked_before_the_origin(client: TestClient):
    res = client.post("/api/games", json=LOBBY, headers={"Host": "evil.example", "Origin": "http://evil.example"})
    assert res.status_code == 400  # the origin matches the host, which is the rebinding case


def test_an_empty_host_is_refused(client: TestClient):
    assert client.get("/api/health", headers={"Host": ""}).status_code == 400


def test_a_foreign_host_is_served_once_configured(settings: Settings):
    with TestClient(create_app(dataclasses.replace(settings, extra_hosts=("invite.example.org",)))) as c:
        assert c.get("/api/health", headers={"Host": "invite.example.org"}).status_code == 200
        assert c.get("/api/health", headers={"Host": "other.example.org"}).status_code == 400


def test_without_extra_hosts_the_test_name_is_refused(settings: Settings):
    with TestClient(create_app(dataclasses.replace(settings, extra_hosts=()))) as c:
        assert c.get("/api/health").status_code == 400  # Host: testserver


# ----------------------------------------------------------------------------------------------------------- the socket


def refused(client: TestClient, path: str, **kwargs) -> int:
    with pytest.raises(WebSocketDisconnect) as raised, client.websocket_connect(path, **kwargs):
        pass
    return raised.value.code


def test_socket_with_the_own_origin_connects(client: TestClient, lan_game):
    gid, token = lan_game
    with connect_game(client, gid, token, headers={"Origin": OWN}) as ws:
        assert ws.receive_json()["type"] in {"lobby", "state"}


def test_socket_with_a_foreign_origin_closes_4403(client: TestClient, lan_game):
    gid, token = lan_game
    assert refused(client, f"/ws/games/{gid}", headers={"Origin": "https://evil.example"}) == 4403
    assert refused(client, f"/ws/games/{gid}", headers={"Origin": "null"}) == 4403
    assert refused(client, f"/ws/games/{gid}", headers={"Origin": "http://testserver.evil.example"}) == 4403


def test_socket_with_no_origin_closes_4403(client: TestClient, lan_game, monkeypatch: pytest.MonkeyPatch):
    gid, token = lan_game
    monkeypatch.setattr(TestClient, "websocket_connect", TestClient.websocket_connect.__wrapped__)  # type: ignore[attr-defined]  # the bare one
    assert refused(client, f"/ws/games/{gid}") == 4403


def test_socket_with_a_dev_origin_connects_only_in_development(client: TestClient, lan_game, tmp_path):
    gid, token = lan_game
    assert refused(client, f"/ws/games/{gid}", headers={"Origin": DEV}) == 4403
    with served(tmp_path, {"FYODOR_DEV_TOOLS": "1"}) as c:
        body = c.post("/api/games", json=LOBBY).json()
        with connect_game(c, body["game"]["id"], body["seat"]["token"], headers={"Origin": DEV}) as ws:
            assert ws.receive_json()["type"] in {"lobby", "state"}


def test_socket_with_a_foreign_host_closes_4400_before_the_origin_is_looked_at(client: TestClient, lan_game):
    gid, token = lan_game
    headers = {"Host": "evil.example", "Origin": "http://evil.example"}
    assert refused(client, f"/ws/games/{gid}", headers=headers) == 4400
    assert refused(client, "/ws/games/nonesuch", headers=headers) == 4400  # not even the game lookup runs first
