"""Bringing my decks (docs/LAN_PLAY.md "Finding a game"): a player who joins from their own Fyodor brings their deck library.

Their server sends it to the host's server (POST /api/lan/send-decks → POST /api/lan/handoff), which keeps it in memory for one
join (?handoff=…) and shows it to that seat alone in the lobby's Choose deck (GET /api/games/{id}/lobby/brought).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import lan as lan_api
from app.config import load_settings
from app.main import create_app
from app.multiplayer import handoff as H
from tests.conftest import claim_host

KRENKO = """Commander
1 Krenko, Mob Boss
Deck
12 Mountain
1 Lightning Bolt
"""


def library(n: int = 1, *, text: str = KRENKO) -> dict:
    return {"from": "DANA-PC", "decks": [{"name": f"Goblins {i}", "commanders": ["Krenko, Mob Boss"], "text": text} for i in range(n)]}


def lan(client: TestClient, ip: str = "192.168.1.20") -> TestClient:
    return TestClient(client.app, client=(ip, 50000))


def offer(client: TestClient, body: dict | bytes, ip: str = "192.168.1.20"):
    data = body if isinstance(body, bytes) else json.dumps(body).encode()
    return lan(client, ip).post("/api/lan/handoff", content=data, headers={"content-type": "application/json"})


@pytest.fixture()
def lobby(client):
    res = client.post("/api/games", json={"mode": "lan", "lobby": True, "name": "Friday", "seats": 4, "players": [{"name": "Alice"}]})
    body = res.json()
    return body["game"]["id"], body["game"]["code"], body["seat"]["token"]


def h(token: str) -> dict[str, str]:
    return {"X-Seat-Token": token}


# --------------------------------------------------------------------------- the store


def test_a_handoff_is_used_once_and_expires():
    now = [0.0]
    store = H.Handoffs(clock=lambda: now[0])
    lib = H.Library(source="DANA-PC", decks=[H.BroughtDeck(name="Goblins", commanders=["Krenko, Mob Boss"], text=KRENKO)])
    token = store.offer(lib, "192.168.1.20")
    assert len(token) >= 20
    assert store.take(token) is lib
    assert store.take(token) is None  # single use
    late = store.offer(lib, "192.168.1.20")
    now[0] += H.TTL + 1
    assert store.take(late) is None  # expired after ten minutes
    assert store.take("not-a-token") is None and store.take("") is None


def test_offers_are_rate_limited_and_capped():
    now = [0.0]
    store = H.Handoffs(clock=lambda: now[0])
    lib = H.Library(source="X", decks=[])
    for _ in range(H.OFFERS_PER_MINUTE):
        store.offer(lib, "192.168.1.20")
    with pytest.raises(H.HandoffRefused) as exc:
        store.offer(lib, "192.168.1.20")
    assert exc.value.status == 429
    now[0] += 61
    for i in range(H.MAX_PENDING):
        store.offer(lib, f"192.168.2.{i}")
    assert len(store.pending) <= H.MAX_PENDING  # the oldest unused offers make room


# --------------------------------------------------------------------------- receiving (the host's server)


def test_the_host_server_takes_a_library_from_a_device_on_the_network(client):
    res = offer(client, library(2))
    assert res.status_code == 200, res.text
    assert res.json()["expires_in"] == H.TTL and isinstance(res.json()["token"], str)
    assert offer(client, library(), ip="8.8.8.8").status_code == 403  # never from outside the local network


def test_a_library_is_size_capped(client):
    assert offer(client, library(H.MAX_DECKS + 1)).status_code == 422
    big = library(H.MAX_DECKS, text="1 Mountain\n" * 4_000)  # 60 lists of 44 KB: over the 2 MB a library may take
    assert offer(client, big).status_code == 413
    assert offer(client, b"{not json").status_code == 422


# --------------------------------------------------------------------------- sending (the player's own server)


@pytest.fixture()
def my_library(client):
    res = client.post("/api/decks", json={"name": "Goblins", "text": KRENKO})
    assert res.status_code == 201, res.text
    return client


def test_only_the_player_s_own_computer_sends_its_library(my_library):
    res = lan(my_library).post("/api/lan/send-decks", json={"url": "http://192.168.1.7:8000"})
    assert res.status_code == 403


@pytest.mark.parametrize("url", ["https://evil.example/x", "http://8.8.8.8:8000", "http://192.168.1.7", "ftp://192.168.1.7:21",
                                 "http://192.168.1.7:8000/api", "http://user@192.168.1.7:8000", "http://host.local:8000"])
def test_the_library_only_goes_to_a_fyodor_on_the_local_network(my_library, url, monkeypatch):
    sent: list[str] = []

    async def fake_post(target: str, path: str, data: bytes) -> dict:
        sent.append(target)
        return {"token": "t" * 24, "missing": []}

    monkeypatch.setattr(lan_api, "post_json", fake_post)
    assert my_library.post("/api/lan/send-decks", json={"url": url}).status_code == 422
    assert sent == []


def test_join_with_my_decks_end_to_end(tmp_path, my_library, monkeypatch, lobby):
    """Dana's own Fyodor sends her library to the host's; the join link's handoff token puts it at her seat alone."""
    host = my_library  # one TestClient app plays both servers here: the host's and Dana's
    gid, code, alice = lobby
    posted: list[dict] = []

    async def to_host(target: str, path: str, data: bytes) -> dict:
        assert target == "http://192.168.1.7:8000"
        if path.endswith("/missing"):
            return lan(host).post(path, content=data, headers={"content-type": "application/json"}).json()
        posted.append(json.loads(data))
        res = offer(host, data)
        assert res.status_code == 200, res.text
        return res.json()

    monkeypatch.setattr(lan_api, "post_json", to_host)
    sent = host.post("/api/lan/send-decks", json={"url": "http://192.168.1.7:8000"})
    assert sent.status_code == 200, sent.text
    token = sent.json()["token"]
    assert sent.json()["decks"] == 1
    assert posted[0]["decks"][0]["name"] == "Goblins" and "Krenko, Mob Boss" in posted[0]["decks"][0]["text"]
    assert posted[0]["decks"][0]["commanders"] == ["Krenko, Mob Boss"]

    dana = lan(host)
    joined = dana.post("/api/join", json={"code": code, "name": "Dana", "handoff": token}).json()
    seat = joined["token"]
    brought = dana.get(f"/api/games/{gid}/lobby/brought", headers=h(seat))
    assert brought.status_code == 200, brought.text
    body = brought.json()
    assert body["from"] == "DANA-PC" or body["from"]  # the sending computer's name
    [deck] = body["decks"]
    assert deck["name"] == "Goblins" and deck["commanders"] == ["Krenko, Mob Boss"] and "Lightning Bolt" in deck["text"]
    assert deck["cover_id"]  # the host has the card database: commander art

    # nobody else sees it: not Alice (the host), not her lobby view, not a spectator
    assert host.get(f"/api/games/{gid}/lobby/brought", headers=h(alice)).json()["decks"] == []
    for view in (host.get(f"/api/games/{gid}/lobby", headers=h(alice)).text, dana.get(f"/api/games/{gid}/lobby", headers=h(seat)).text):
        assert "Lightning Bolt" not in view and "Goblins" not in view
    spectator = dana.post("/api/join", json={"code": code, "spectate": True}).json()["token"]
    assert dana.get(f"/api/games/{gid}/lobby/brought", headers=h(spectator)).status_code == 403
    assert dana.get(f"/api/games/{gid}/lobby/brought").status_code == 403

    # the token was used: a second join with it brings nothing
    again = dana.post("/api/join", json={"code": code, "name": "Eve", "handoff": token}).json()
    assert dana.get(f"/api/games/{gid}/lobby/brought", headers=h(again["token"])).json()["decks"] == []

    # choosing one goes through the lobby's personal import, as a pasted list does
    imported = dana.post(f"/api/games/{gid}/lobby/import", json={"name": deck["name"], "text": deck["text"]}, headers=h(seat))
    assert imported.status_code == 200, imported.text
    chosen = dana.post(f"/api/games/{gid}/lobby/deck", json={"name": deck["name"], "text": deck["text"]}, headers=h(seat))
    assert chosen.status_code == 200, chosen.text

    # leaving the seat drops it
    assert dana.post(f"/api/games/{gid}/lobby/leave", headers=h(seat)).status_code == 204
    assert gid not in {k[0] for k in host.app.state.services.handoffs.attached} or all(
        k[1] != seat for k in host.app.state.services.handoffs.attached)


def test_the_library_is_dropped_when_the_game_starts(my_library, lobby, monkeypatch):
    host = my_library
    gid, code, alice = lobby
    token = offer(host, library()).json()["token"]
    dana = lan(host)
    seat = dana.post("/api/join", json={"code": code, "name": "Dana", "handoff": token}).json()["token"]
    assert len(dana.get(f"/api/games/{gid}/lobby/brought", headers=h(seat)).json()["decks"]) == 1
    for t in (alice, seat):
        assert host.post(f"/api/games/{gid}/lobby/deck", json={"text": KRENKO}, headers=h(t)).status_code == 200
    assert host.post(f"/api/games/{gid}/lobby/start", json={"force": True}, headers=h(alice)).status_code == 200
    assert host.app.state.services.handoffs.attached == {}
    assert dana.get(f"/api/games/{gid}/lobby/brought", headers=h(seat)).json()["decks"] == []


def test_nothing_is_saved_or_logged(my_library, lobby, caplog, tmp_path):
    host = my_library
    gid, code, alice = lobby
    caplog.set_level("DEBUG")
    token = offer(host, library()).json()["token"]
    host.post("/api/join", json={"code": code, "name": "Dana", "handoff": token})
    host.post(f"/api/games/{gid}/save", json={"name": "check"})
    assert token not in caplog.text and "Lightning Bolt" not in caplog.text
    data_dir = Path(host.app.state.services.settings.data_dir)
    for f in data_dir.rglob("*"):
        if f.is_file() and f.suffix in (".json", ".jsonl", ".sqlite", ".log"):
            assert token.encode() not in f.read_bytes()


def test_a_library_from_an_empty_computer_sends_nothing(tmp_path, monkeypatch):
    settings = load_settings({"FYODOR_DATA_DIR": str(tmp_path / "empty"), "FYODOR_FRONTEND_DIST": str(tmp_path / "nodist")})

    async def boom(target: str, path: str, data: bytes) -> dict:
        raise AssertionError("nothing to send")

    monkeypatch.setattr(lan_api, "post_json", boom)
    with TestClient(create_app(settings)) as c:
        claim_host(c)
        res = c.post("/api/lan/send-decks", json={"url": "http://192.168.1.7:8000"})
        assert res.status_code == 200 and res.json() == {"token": None, "decks": 0, "cards": 0}


def test_an_unreachable_host_is_a_clear_error(my_library, monkeypatch):
    import httpx

    async def down(target: str, path: str, data: bytes) -> dict:
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(lan_api, "post_json", down)
    res = my_library.post("/api/lan/send-decks", json={"url": "http://192.168.1.7:8000"})
    assert res.status_code == 502 and "reach" in res.json()["detail"]
