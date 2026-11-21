"""Finding Fyodor tables on the network (docs/LAN_PLAY.md "Finding a game"): the UDP beacon and GET /api/lan/nearby.

Everything runs on 127.0.0.1 with free ports: no real broadcast is ever sent.
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import launcher
from app.config import load_settings
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.visibility import SPECTATOR
from app.main import create_app
from app.multiplayer import discovery as D
from app.multiplayer.elimination import PracticeLink
from tests.conftest import claim_host

BOB_DECK = """Commander
1x Krenko, Mob Boss (ddn) 13
Deck
12x Mountain (cmm) 1003
1x Lightning Bolt (clb) 187
"""


def lan_settings(tmp_path: Path, **extra: str):
    env = {"FYODOR_DATA_DIR": str(tmp_path / "data"), "FYODOR_FRONTEND_DIST": str(tmp_path / "nodist"),
           "FYODOR_HOST": "0.0.0.0", "FYODOR_DISCOVERY_PORT": "0", **extra}
    return load_settings(env)


@pytest.fixture()
def lan_client(tmp_path, card_db):
    """A server listening on the LAN (its beacon on a free port), with the fixture card database (same data dir as ``card_db``)."""
    with TestClient(create_app(lan_settings(tmp_path))) as c:
        claim_host(c)
        yield c


@pytest.fixture()
def bare_lan_client(tmp_path):
    """The same without a card database: enough for the beacon itself."""
    with TestClient(create_app(lan_settings(tmp_path))) as c:
        claim_host(c)
        yield c


def send(port: int, payload: bytes, *, timeout: float = 0.3, count: int = 1) -> list[bytes]:
    """Send a datagram to 127.0.0.1:port ``count`` times and collect whatever comes back within ``timeout``."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        s.settimeout(timeout)
        for _ in range(count):
            s.sendto(payload, ("127.0.0.1", port))
        got: list[bytes] = []
        while True:
            try:
                got.append(s.recv(65536))
            except TimeoutError:
                return got


def ask(port: int, **extra) -> list[dict]:
    query = {"fyodor": "find", "v": 1, "nonce": "abc123", **extra}
    return [json.loads(x) for x in send(port, json.dumps(query).encode())]


def beacon_port(client: TestClient) -> int:
    port = client.app.state.discovery.port
    assert port, "the responder should be listening in LAN mode"
    return port


def open_tables(client: TestClient) -> dict[str, str]:
    """A LAN lobby with a password (Bob has brought a deck), a hot-seat game and a practice table."""
    res = client.post("/api/games", json={"mode": "lan", "lobby": True, "name": "Thursday Commander", "seats": 4,
                                          "password": "s3cret", "players": [{"name": "Alice"}]})
    assert res.status_code == 201, res.text
    lobby = res.json()
    bob = client.post("/api/join", json={"code": lobby["game"]["code"], "name": "Bob", "password": "s3cret"}).json()
    deck = client.post(f"/api/games/{lobby['game']['id']}/lobby/deck", json={"text": BOB_DECK, "name": "Goblins"},
                       headers={"X-Seat-Token": bob["token"]})
    assert deck.status_code == 200, deck.text
    hot = client.post("/api/games", json={"mode": "local", "name": "Kitchen table", "players": [{"name": "Ann"}, {"name": "Ben"}]})
    assert hot.status_code == 201, hot.text
    hub = client.app.state.services.hub
    practice = hub.create_practice(GameSession(new_game([PlayerSetup(name="Carol")], name="Carol practice")),
                                   PracticeLink(live=lobby["game"]["id"], seat="p3", game=1))
    return {"lobby": lobby["game"]["id"], "code": lobby["game"]["code"], "hot": hot.json()["game"]["id"], "practice": practice.id}


# --------------------------------------------------------------------------- when the beacon runs


def test_the_beacon_runs_only_on_a_lan_server_with_discovery_on(tmp_path):
    assert D.enabled(lan_settings(tmp_path))
    assert D.enabled(lan_settings(tmp_path, FYODOR_HOST="192.168.1.5"))
    for host in ("127.0.0.1", "localhost", "::1"):  # --local: only this computer can connect
        assert not D.enabled(lan_settings(tmp_path, FYODOR_HOST=host))
    assert not D.enabled(lan_settings(tmp_path, FYODOR_DISCOVERY="0"))
    default = load_settings({"FYODOR_DATA_DIR": str(tmp_path / "d")})
    assert default.discovery and default.discovery_port == D.DEFAULT_PORT == 47474


def test_no_responder_in_local_mode_or_when_turned_off(tmp_path):
    for extra in ({"FYODOR_HOST": "127.0.0.1"}, {"FYODOR_DISCOVERY": "0"}):
        with TestClient(create_app(lan_settings(tmp_path, **extra))) as c:
            claim_host(c)
            assert c.app.state.discovery.port is None


def test_a_port_already_taken_is_logged_once_and_never_stops_the_server(tmp_path, caplog):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as squatter:
        squatter.bind(("", 0))  # no SO_REUSEADDR: nobody else may share it
        port = squatter.getsockname()[1]
        caplog.set_level(logging.INFO, logger="app.multiplayer.discovery")
        with TestClient(create_app(lan_settings(tmp_path, FYODOR_DISCOVERY_PORT=str(port)))) as c:
            claim_host(c)
            assert c.app.state.discovery.port is None
            assert c.get("/api/health").status_code == 200
    warnings = [r for r in caplog.records if r.name == "app.multiplayer.discovery" and r.levelno >= logging.WARNING]
    assert len(warnings) == 1 and str(port) in warnings[0].getMessage()


# --------------------------------------------------------------------------- what a reply contains


def test_a_reply_lists_only_lan_tables_and_only_what_another_device_sees(lan_client):
    ids = open_tables(lan_client)
    replies = ask(beacon_port(lan_client))
    assert len(replies) == 1
    reply = replies[0]
    assert reply["fyodor"] == "here" and reply["v"] == 1 and reply["nonce"] == "abc123"
    assert reply["id"] == lan_client.app.state.discovery.instance_id
    assert reply["port"] == lan_client.app.state.services.settings.port and reply["version"]
    assert reply["name"] == D.computer_name()
    assert [t["id"] for t in reply["tables"]] == [ids["lobby"]]  # never the hot-seat or the practice table
    table = reply["tables"][0]
    assert table == {"id": ids["lobby"], "name": "Thursday Commander", "format": "commander", "phase": "lobby", "code": ids["code"],
                     "has_password": True, "seats": 4, "taken": 2, "open": 2, "players": ["Alice", "Bob"], "turn": 0}
    raw = json.dumps({k: v for k, v in reply.items() if k != "name"})  # (the computer's own name is whatever it is)
    for secret in ("Krenko", "Mountain", "Lightning Bolt", "Goblins", "s3cret", "token", "deck", "hand"):
        assert secret not in raw
    # the same as GET /api/games shows a device on the LAN
    remote = TestClient(lan_client.app, client=("192.168.1.20", 50000))
    listed = {g["id"]: g for g in remote.get("/api/games").json()}
    assert set(listed) == {ids["lobby"]}
    assert listed[ids["lobby"]]["code"] == table["code"] and listed[ids["lobby"]]["has_password"]


def test_a_game_in_progress_shows_its_turn_and_every_player(lan_client):
    res = lan_client.post("/api/games", json={"mode": "lan", "name": "Late game", "players": [{"name": "Ann"}, {"name": "Ben"}]})
    gid = res.json()["game"]["id"]
    [table] = ask(beacon_port(lan_client))[0]["tables"]
    assert table["id"] == gid and table["phase"] == "playing" and table["turn"] == 1
    assert table["players"] == ["Ann", "Ben"] and table["seats"] == 2 and table["taken"] == 1 and table["open"] == 1
    assert not table["has_password"]


def test_open_lobbies_come_first():
    tables = [
        {"id": "a", "phase": "playing", "open": 1, "name": "A"},
        {"id": "b", "phase": "lobby", "open": 0, "name": "B"},
        {"id": "c", "phase": "lobby", "open": 2, "name": "C"},
    ]
    assert [t["id"] for t in D.order_tables(tables)] == ["c", "b", "a"]


def test_a_reply_stays_under_the_size_cap():
    tables = [{"id": f"{i:016x}", "name": "N" * 80, "format": "commander", "phase": "lobby", "code": "ABCDEF", "has_password": False,
               "seats": 6, "taken": 6, "open": 0, "players": ["P" * 40] * 6, "turn": 0} for i in range(60)]
    data = D.encode_reply("n" * 16, instance="i" * 16, name="DESKTOP-42", port=8000, version="0.1.0", tables=tables)
    assert len(data) <= D.MAX_REPLY
    body = json.loads(data)
    assert 0 < len(body["tables"]) < 60 and body["more"] == 60 - len(body["tables"])
    assert body["tables"] == tables[: len(body["tables"])]


# --------------------------------------------------------------------------- what the responder ignores


@pytest.mark.parametrize("payload", [
    b"hello",
    b"{not json",
    b"[1, 2, 3]",
    json.dumps({"fyodor": "nope", "v": 1, "nonce": "x"}).encode(),
    json.dumps({"other": "find", "v": 1, "nonce": "x"}).encode(),
    json.dumps({"fyodor": "find", "v": 2, "nonce": "x"}).encode(),
    json.dumps({"fyodor": "find", "v": 1}).encode(),
    json.dumps({"fyodor": "find", "v": 1, "nonce": 5}).encode(),
    json.dumps({"fyodor": "find", "v": 1, "nonce": "x" * 200}).encode(),
    json.dumps({"fyodor": "here", "v": 1, "nonce": "x", "id": "y", "tables": []}).encode(),
    json.dumps({"fyodor": "find", "v": 1, "nonce": "x", "pad": "z" * 9000}).encode(),  # oversized
])
def test_malformed_foreign_and_oversized_datagrams_get_no_answer(bare_lan_client, payload):
    assert send(beacon_port(bare_lan_client), payload, timeout=0.15) == []


def test_a_server_never_answers_its_own_query(bare_lan_client):
    own = bare_lan_client.app.state.discovery.instance_id
    assert ask(beacon_port(bare_lan_client), id=own) == []
    assert len(ask(beacon_port(bare_lan_client), id="someone-else")) == 1


def test_replies_are_rate_limited_per_sender(bare_lan_client):
    query = json.dumps({"fyodor": "find", "v": 1, "nonce": "flood"}).encode()
    replies = send(beacon_port(bare_lan_client), query, count=20, timeout=0.3)
    assert 1 <= len(replies) <= D.RATE_PER_SECOND


def test_only_devices_on_the_local_network_get_an_answer(tmp_path):
    d = D.Discovery(lan_settings(tmp_path), lambda: [])
    query = D.encode_query("n1")
    for sender in ("192.168.1.20", "10.1.2.3", "172.16.0.9", "169.254.3.4", "127.0.0.1", "fd00::5"):
        assert d.answer(query, sender) is not None, sender
    for sender in ("8.8.8.8", "100.64.0.1", "2001:4860::8888", "not an ip"):  # never a reflector for the Internet
        assert d.answer(query, sender) is None, sender


def test_the_rate_limit_forgets_quiet_senders():
    limit = D.RateLimit(per_second=2, max_senders=3)
    assert limit.allow("a", now=0.0) and limit.allow("a", now=0.1) and not limit.allow("a", now=0.2)
    assert limit.allow("a", now=1.2)
    for ip in ("b", "c", "d", "e"):
        limit.allow(ip, now=5.0)
    assert len(limit.seen) <= 3


# --------------------------------------------------------------------------- asking


def test_query_finds_a_server_once_and_skips_our_own(tmp_path, lan_client):
    ids = open_tables(lan_client)
    port = beacon_port(lan_client)
    other = lan_client.app.state.discovery.instance_id
    targets = [("127.0.0.1", port), ("127.0.0.1", port)]  # two broadcasts reaching the same server: one entry
    found = asyncio.run(D.query(targets, timeout=0.3, exclude="me"))
    assert len(found) == 1
    server = found[0]
    assert server["id"] == other and server["url"] == f"http://127.0.0.1:{lan_client.app.state.services.settings.port}"
    assert [t["code"] for t in server["tables"]] == [ids["code"]]
    assert asyncio.run(D.query(targets, timeout=0.2, exclude=other)) == []  # our own server is not "a game nearby"


def test_query_with_no_network_finds_nothing(monkeypatch):
    def no_network(*_a, **_k):
        raise OSError(101, "Network is unreachable")

    monkeypatch.setattr(D, "_udp_socket", no_network)
    assert asyncio.run(D.query([("255.255.255.255", 47474)], timeout=0.1)) == []
    assert asyncio.run(D.query([], timeout=0.05)) == []


def test_replies_from_the_network_are_checked_before_use():
    good = {"fyodor": "here", "v": 1, "nonce": "n1", "id": "srv", "name": "DESKTOP-42", "port": 8000, "version": "0.1.0", "tables": [
        {"id": "g1", "name": "Thursday", "format": "commander", "phase": "lobby", "code": "ABC123", "has_password": False,
         "seats": 4, "taken": 1, "open": 3, "players": ["Alice"], "turn": 0},
        {"id": "g2", "name": "Bad code", "format": "commander", "phase": "lobby", "code": "../x?y", "has_password": False,
         "seats": 4, "taken": 1, "open": 3, "players": ["Alice"], "turn": 0},
        "not a table",
    ]}
    parsed = D.parse_reply(json.dumps(good).encode(), "n1", "192.168.1.7")
    assert parsed is not None and parsed["url"] == "http://192.168.1.7:8000"
    assert [t["id"] for t in parsed["tables"]] == ["g1"]
    assert D.parse_reply(json.dumps(good).encode(), "other-nonce", "192.168.1.7") is None
    for bad in ({**good, "port": "8000"}, {**good, "port": 0}, {**good, "port": True}, {**good, "v": 2}, {**good, "fyodor": "find"},
                {**good, "id": 5}, {**good, "tables": "x"}):
        assert D.parse_reply(json.dumps(bad).encode(), "n1", "192.168.1.7") is None
    assert D.parse_reply(b"\xff\xfe", "n1", "192.168.1.7") is None


def test_broadcast_targets_cover_every_lan_address():
    assert D.broadcast_targets(47474, ["192.168.1.7", "10.0.0.20", "192.168.1.9"]) == [
        ("255.255.255.255", 47474), ("192.168.1.255", 47474), ("10.0.0.255", 47474)]
    assert D.broadcast_targets(47474, []) == [("255.255.255.255", 47474)]


# --------------------------------------------------------------------------- GET /api/lan/nearby


def test_nearby_is_for_the_host_computer_only(bare_lan_client):
    remote = TestClient(bare_lan_client.app, client=("192.168.1.20", 50000))
    assert remote.get("/api/lan/nearby").status_code == 403


def test_nearby_lists_other_servers_and_never_this_one(tmp_path, lan_client, card_db):
    ids = open_tables(lan_client)
    other_port = beacon_port(lan_client)
    me_settings = lan_settings(tmp_path / "me")
    with TestClient(create_app(me_settings)) as me:
        claim_host(me)
        own = beacon_port(me)
        me.app.state.discovery.targets = lambda: [("127.0.0.1", other_port), ("127.0.0.1", own)]
        me.app.state.discovery.timeout = 0.3
        res = me.get("/api/lan/nearby")
        assert res.status_code == 200, res.text
        [server] = res.json()
        assert set(server) == {"name", "url", "version", "tables"}
        assert server["url"].endswith(f":{lan_client.app.state.services.settings.port}")
        assert [t["code"] for t in server["tables"]] == [ids["code"]] and server["tables"][0]["has_password"]


def test_nearby_shares_one_scan_between_polling_clients(tmp_path, monkeypatch):
    scans: list[int] = []

    async def fake_query(targets, *, timeout, exclude=None):
        scans.append(1)
        await asyncio.sleep(0.05)
        return []

    monkeypatch.setattr(D, "query", fake_query)
    with TestClient(create_app(lan_settings(tmp_path, FYODOR_DISCOVERY="0"))) as c:
        claim_host(c)
        assert c.get("/api/lan/nearby").json() == []  # discovery off: no scan at all
        assert scans == []
    with TestClient(create_app(lan_settings(tmp_path / "on"))) as c:
        claim_host(c)
        assert c.get("/api/lan/nearby").json() == [] and c.get("/api/lan/nearby").json() == []
        assert len(scans) == 1


def test_nearby_with_no_network_is_an_empty_list(tmp_path, monkeypatch):
    with TestClient(create_app(lan_settings(tmp_path))) as c:
        claim_host(c)
        monkeypatch.setattr(D, "_udp_socket", lambda *a, **k: (_ for _ in ()).throw(OSError(101, "Network is unreachable")))
        c.app.state.discovery.timeout = 0.05
        res = c.get("/api/lan/nearby")
        assert res.status_code == 200 and res.json() == []


def test_lan_info_says_whether_discovery_is_on(tmp_path):
    with TestClient(create_app(lan_settings(tmp_path))) as c:
        claim_host(c)
        info = c.get("/api/lan-info").json()
        assert info["discovery"] is True and info["discovery_port"] == c.app.state.discovery.port
    with TestClient(create_app(lan_settings(tmp_path / "off", FYODOR_DISCOVERY="0"))) as c:
        claim_host(c)
        assert c.get("/api/lan-info").json()["discovery"] is False


# --------------------------------------------------------------------------- joining what was found


def test_a_found_table_is_joined_with_its_code_and_the_name_from_the_link(lan_client):
    """The Play page's ?code=…&name=…&join=1 link: the found code and the visitor's name seat them in the lobby."""
    res = lan_client.post("/api/games", json={"mode": "lan", "lobby": True, "name": "Open night", "seats": 3, "players": [{"name": "Alice"}]})
    host = res.json()
    [table] = ask(beacon_port(lan_client))[0]["tables"]
    remote = TestClient(lan_client.app, client=("192.168.1.20", 50000))
    joined = remote.post("/api/join", json={"code": table["code"], "name": "Dana"})
    assert joined.status_code == 200, joined.text
    body = joined.json()
    assert body["game_id"] == host["game"]["id"] and body["viewer"] == "p2"
    lobby = remote.get(f"/api/games/{body['game_id']}/lobby", headers={"X-Seat-Token": body["token"]}).json()
    assert [s["name"] for s in lobby["seats"] if s["claimed"]] == ["Alice", "Dana"]
    watch = remote.post("/api/join", json={"code": table["code"], "spectate": True})
    assert watch.status_code == 200 and watch.json()["viewer"] == SPECTATOR
    [after] = ask(beacon_port(lan_client))[0]["tables"]
    assert after["taken"] == 2 and after["open"] == 1 and after["players"] == ["Alice", "Dana"]


# --------------------------------------------------------------------------- the launcher


def test_the_launcher_tells_the_host_friends_will_find_the_table(tmp_path, monkeypatch, capsys):
    dist = tmp_path / "dist"
    dist.mkdir()
    for k, v in {"FYODOR_DATA_DIR": str(tmp_path / "d"), "FYODOR_FRONTEND_DIST": str(dist)}.items():
        monkeypatch.setenv(k, v)
    import uvicorn

    import tools.update_cards

    monkeypatch.setattr(tools.update_cards, "main", lambda argv: 0)
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: None)
    # never really serve: the launcher runs its own uvicorn.Server, which would wait for Ctrl+C forever
    monkeypatch.setattr(launcher, "serve", lambda settings, browser=False: None)
    monkeypatch.setattr(launcher, "lan_addresses", lambda: ["192.168.1.7"])
    launcher.main(["--port", "0", "--no-browser"])
    out = capsys.readouterr().out
    assert "Games on your network" in out and "UDP 47474" in out
    launcher.main(["--port", "0", "--no-browser", "--local"])
    assert "Games on your network" not in capsys.readouterr().out
