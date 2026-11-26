"""-- deck sharing -- (app/decks/sharing.py): friends on the network browse the decks this computer shares (GET /api/lan/decks)
and copy one. Off by default; then all decks or only the ones marked Shared; never notes or anything but the card lists."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from app.api import lan as lan_api

KRENKO = "Commander\n1 Krenko, Mob Boss\nDeck\n12 Mountain\n1 Lightning Bolt\n"
SECRET = "Mull to Krenko; my secret plan"


def lan(client: TestClient, ip: str = "192.168.1.20") -> TestClient:
    return TestClient(client.app, client=(ip, 50000))


def two_decks(client: TestClient) -> tuple[str, str]:
    ids = []
    for name in ("Goblins", "Hidden"):
        deck = client.post("/api/decks", json={"text": KRENKO, "name": name}).json()
        client.put(f"/api/decks/{deck['id']}", json={**deck, "notes": SECRET})
        ids.append(deck["id"])
    return ids[0], ids[1]


def test_nothing_is_shared_until_the_owner_turns_it_on(client):
    goblins, _ = two_decks(client)
    assert client.get("/api/decks/sharing").json() == {"enabled": False, "all": False}
    client.put(f"/api/decks/{goblins}/shared", json={"shared": True})  # marked, but sharing itself is still off
    res = lan(client).get("/api/lan/decks")
    assert res.status_code == 404
    assert "Goblins" not in res.text and "Mountain" not in res.text


def test_only_marked_decks_and_only_their_lists_leave(client):
    goblins, _ = two_decks(client)
    assert client.put(f"/api/decks/{goblins}/shared", json={"shared": True}).json() == {"id": goblins, "shared": True}
    assert client.put("/api/decks/sharing", json={"enabled": True}).json() == {"enabled": True, "all": False}
    res = lan(client).get("/api/lan/decks")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"from", "decks"}
    assert [d["name"] for d in body["decks"]] == ["Goblins"]
    assert set(body["decks"][0]) == {"name", "commanders", "text"}
    assert body["decks"][0]["commanders"] == ["Krenko, Mob Boss"] and "12 Mountain" in body["decks"][0]["text"]
    assert SECRET not in res.text and "Hidden" not in res.text
    # the shelf knows which decks are shared; the flag survives a save of the list
    assert {d["name"]: d["shared"] for d in client.get("/api/decks").json()} == {"Goblins": True, "Hidden": False}
    deck = client.get(f"/api/decks/{goblins}").json()
    client.put(f"/api/decks/{goblins}", json={k: deck[k] for k in ("name", "format", "notes", "entries", "categories")})
    assert client.get(f"/api/decks/{goblins}").json()["shared"] is True


def test_share_all_and_turning_it_off_again(client):
    two_decks(client)
    client.put("/api/decks/sharing", json={"enabled": True, "all": True})
    assert sorted(d["name"] for d in lan(client).get("/api/lan/decks").json()["decks"]) == ["Goblins", "Hidden"]
    client.put("/api/decks/sharing", json={"enabled": False, "all": True})
    assert lan(client).get("/api/lan/decks").status_code == 404


def test_only_the_local_network_and_only_the_owner_changes_it(client):
    two_decks(client)
    client.put("/api/decks/sharing", json={"enabled": True, "all": True})
    assert lan(client, "8.8.8.8").get("/api/lan/decks").status_code == 403
    # another device on the LAN can read what is shared, but can't turn sharing on or mark decks
    assert lan(client).put("/api/decks/sharing", json={"enabled": True, "all": True}).status_code == 403
    assert lan(client).get("/api/decks/sharing").status_code == 403
    assert lan(client).get("/api/lan/friend-decks", params={"url": "http://192.168.1.30:8000"}).status_code == 403


def test_browsing_a_friend_goes_server_to_server_on_the_lan_only(client, monkeypatch):
    goblins, _ = two_decks(client)
    client.put(f"/api/decks/{goblins}/shared", json={"shared": True})
    client.put("/api/decks/sharing", json={"enabled": True})
    asked: list[str] = []
    real = httpx.AsyncClient

    def friend(**kw):  # the "friend" is this same app, reached as a LAN computer
        asked.append("x")
        return real(transport=httpx.ASGITransport(app=client.app, client=("192.168.1.30", 40000)), timeout=kw.get("timeout"))

    monkeypatch.setattr(lan_api.httpx, "AsyncClient", friend)
    assert client.get("/api/lan/friend-decks", params={"url": "http://93.184.216.34:8000"}).status_code == 422  # not the LAN
    assert not asked
    res = client.get("/api/lan/friend-decks", params={"url": "http://192.168.1.30:8000"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["url"] == "http://192.168.1.30:8000" and [d["name"] for d in body["decks"]] == ["Goblins"]
    assert SECRET not in res.text
    client.put("/api/decks/sharing", json={"enabled": False})
    assert client.get("/api/lan/friend-decks", params={"url": "http://192.168.1.30:8000"}).status_code == 404
