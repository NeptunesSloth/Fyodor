"""The offline game-night path (docs/LAN_PLAY.md "Finding a game"): a friend saves decks on their own Fyodor while online, then
joins over the LAN with no internet and plays their deck.

- card records the host's (older) card database lacks travel with the handoff, Scryfall-shaped, checked, add-only;
- the art the host lacks comes from the friend's server over the LAN once they pick a deck;
- saving a deck while online keeps its art for offline play (the art keeper), retrying when back online.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import lan as lan_api
from app.cards import share
from app.cards.art_keeper import ArtKeeper
from app.cards.importer import build_database
from app.config import load_settings
from app.main import create_app
from app.multiplayer import lan_art
from tests.fixtures.cards import fixture_cards, newer_set_card

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"
NEW = newer_set_card()


def h(token: str) -> dict[str, str]:
    return {"X-Seat-Token": token}


# --------------------------------------------------------------------------- card records


def test_a_card_record_round_trips_scryfall_shaped(cards):
    """What one Fyodor sends is a Scryfall card (never a database row), and reads back as the same printing."""
    krenko = cards.resolve("Krenko, Mob Boss")
    rows = share.records(cards, [krenko["id"]])
    [record] = rows
    assert record["object"] == "card" and record["set"] == "ddn" and record["name"] == "Krenko, Mob Boss"
    assert "set_code" not in record and "is_token" not in record  # Scryfall's field names
    assert share.clean_card(record) is not None
    delver = cards.resolve("Delver of Secrets")
    [dfc] = share.records(cards, [delver["id"]])
    assert [f["name"] for f in dfc["card_faces"]] == ["Delver of Secrets", "Insectile Aberration"]


def test_records_are_checked_before_use():
    assert share.clean_card(NEW) is not None
    for bad in ({**NEW, "id": "not-a-uuid"}, {**NEW, "object": "set"}, {**NEW, "name": 5}, {**NEW, "colors": "R"},
                {**NEW, "cmc": "two"}, {**NEW, "legalities": []}, {**NEW, "oracle_text": "x" * 20_000}, "card", None,
                {k: v for k, v in NEW.items() if k != "oracle_id"}):
        assert share.clean_card(bad) is None, bad
    # unknown fields are dropped, image links kept only to Scryfall's image host
    cleaned = share.clean_card({**NEW, "evil": "<script>", "image_uris": {"normal": "http://attacker.example/x.jpg"}})
    assert cleaned is not None and "evil" not in cleaned and "image_uris" not in cleaned


def test_new_cards_are_added_and_known_ones_never_overwritten(cards):
    krenko = cards.resolve("Krenko, Mob Boss")
    [record] = share.records(cards, [krenko["id"]])
    forged = {**record, "oracle_text": "Win the game."}
    reprint_of_other = {**NEW, "id": "11111111-1111-4111-8111-111111111111", "oracle_id": krenko["oracle_id"], "name": "Not Krenko"}
    result = share.add_cards(cards, [NEW, forged, reprint_of_other, {"object": "card"}])
    assert result.added == ["Zephyr of the New Set"]
    assert {r["why"] for r in result.rejected} >= {"its card data couldn't be read"}
    assert any(r["name"] == "Not Krenko" for r in result.rejected)
    assert cards.resolve("Krenko, Mob Boss")["oracle_text"].startswith("{T}: Create X")  # never overwritten
    zephyr = cards.resolve("Zephyr of the New Set")
    assert zephyr is not None and zephyr["id"] == NEW["id"]
    assert cards.resolve("Zephyr of the New Set", "nws", "7")["id"] == NEW["id"]
    assert cards.search("Zephyr")  # findable like any other card
    assert share.add_cards(cards, [NEW]).added == []  # a second time adds nothing


# --------------------------------------------------------------------------- the two servers


def server_settings(root: Path, cards_list: list[dict]) -> object:
    s = load_settings({"FYODOR_DATA_DIR": str(root), "FYODOR_FRONTEND_DIST": str(root / "nodist"), "FYODOR_ALLOW_NETWORK": "0"})
    s.ensure_dirs()
    build_database(cards_list, s.cards_db_path, meta={"bulk_type": "test"})
    return s


@pytest.fixture()
def pod(tmp_path):
    """The host (an older card database without the new card) and the friend (newer, with the card and its art cached)."""
    host_s = server_settings(tmp_path / "host", fixture_cards())
    friend_s = server_settings(tmp_path / "friend", [*fixture_cards(), NEW])
    with TestClient(create_app(host_s)) as host, TestClient(create_app(friend_s)) as friend:
        art = friend.app.state.services.images.path_for(NEW["id"])
        art.parent.mkdir(parents=True, exist_ok=True)
        art.write_bytes(JPEG)
        yield host, friend


def peer(server: TestClient, address: tuple[str, int]) -> TestClient:
    """Another device's requests to ``server``, run on that server's own event loop (as a real server serves every client
    from one loop). A bare ``TestClient(app)`` would run each request on a fresh loop of its own, while the app's background
    tasks and state belong to the server's loop: on Windows that cross-loop use now and then loses a wake-up and the
    teardown waits forever."""
    other = TestClient(server.app, client=address)
    other.portal = server.portal
    return other


def wire(monkeypatch, host: TestClient, friend: TestClient) -> None:
    """The LAN between them: the friend's server reaches the host's at 192.168.1.7:8000; the host reaches back at 192.168.1.20."""
    to_host = TestClient(host.app, client=("192.168.1.20", 50000))

    async def post(target: str, path: str, data: bytes) -> dict:
        assert target == "http://192.168.1.7:8000"
        res = to_host.post(path, content=data, headers={"content-type": "application/json"})
        if res.status_code == 404:
            raise httpx.HTTPStatusError("no such endpoint", request=httpx.Request("POST", target), response=httpx.Response(404))
        res.raise_for_status()
        return res.json()

    monkeypatch.setattr(lan_api, "post_json", post)

    def friend_transport() -> httpx.MockTransport:
        def handle(req: httpx.Request) -> httpx.Response:
            assert req.url.host == "192.168.1.20"
            # asked from the host's worker thread: a loop of its own for each request (the image route keeps no loop state),
            # never a blocking call into the friend's main loop from another thread while both servers are busy
            res = TestClient(friend.app).get(req.url.path, params=dict(req.url.params))
            return httpx.Response(res.status_code, content=res.content, headers={"content-type": res.headers.get("content-type", "")})
        return httpx.MockTransport(handle)

    monkeypatch.setattr(lan_art, "transport", friend_transport)


def test_offline_join_brings_unknown_cards_and_their_art(pod, monkeypatch):
    host, friend = pod
    wire(monkeypatch, host, friend)
    deck_text = "Commander\n1 Zephyr of the New Set (NWS) 7\nDeck\n1 Sol Ring\n10 Mountain\n"
    assert friend.post("/api/decks", json={"name": "New toys", "text": deck_text}).status_code == 201
    assert host.app.state.services.cards.resolve("Zephyr of the New Set") is None  # the host's database is older

    lobby = host.post("/api/games", json={"mode": "lan", "lobby": True, "name": "Night", "seats": 4, "players": [{"name": "Alice"}]}).json()
    gid, code = lobby["game"]["id"], lobby["game"]["code"]
    sent = friend.post("/api/lan/send-decks", json={"url": "http://192.168.1.7:8000"})
    assert sent.status_code == 200, sent.text
    assert sent.json()["cards"] == 1  # only what the host lacked travelled

    dana = peer(host, ("192.168.1.20", 50000))
    seat = dana.post("/api/join", json={"code": code, "name": "Dana", "handoff": sent.json()["token"]}).json()["token"]
    assert host.app.state.services.cards.resolve("Zephyr of the New Set")["id"] == NEW["id"]  # added on the join
    brought = dana.get(f"/api/games/{gid}/lobby/brought", headers=h(seat)).json()
    [deck] = brought["decks"]
    assert deck["cover_id"] == NEW["id"] and brought["unknown"] == []

    res = dana.post(f"/api/games/{gid}/lobby/deck", json={"name": deck["name"], "text": deck["text"]}, headers=h(seat))
    assert res.status_code == 200, res.text
    mine = next(s for s in res.json()["seats"] if s["id"] == "p2")["deck"]
    assert mine["report"]["unresolved"] == [] and mine["commanders"] == ["Zephyr of the New Set"]
    # the art comes over the LAN in the background
    for _ in range(100):
        if host.app.state.services.images.has(NEW["id"]):
            break
        time.sleep(0.05)
    assert host.app.state.services.images.has(NEW["id"])
    assert host.get(f"/api/images/{NEW['id']}").content == JPEG


def test_a_host_without_the_card_lookup_still_gets_the_decks(pod, monkeypatch):
    """An older host with no /lan/handoff/missing: the decks come anyway; the lobby names what it can't resolve, and why."""
    host, friend = pod
    wire(monkeypatch, host, friend)
    friend.post("/api/decks", json={"name": "New toys", "text": "Commander\n1 Zephyr of the New Set (NWS) 7\nDeck\n10 Mountain\n"})
    real = lan_api.post_json

    async def old_host(target: str, path: str, data: bytes) -> dict:
        if path.endswith("/missing"):
            raise httpx.HTTPStatusError("404", request=httpx.Request("POST", target), response=httpx.Response(404))
        return await real(target, path, data)

    monkeypatch.setattr(lan_api, "post_json", old_host)
    sent = friend.post("/api/lan/send-decks", json={"url": "http://192.168.1.7:8000"}).json()
    assert sent["cards"] == 0 and sent["decks"] == 1
    lobby = host.post("/api/games", json={"mode": "lan", "lobby": True, "name": "Night", "players": [{"name": "Alice"}]}).json()
    dana = peer(host, ("192.168.1.20", 50000))
    seat = dana.post("/api/join", json={"code": lobby["game"]["code"], "name": "Dana", "handoff": sent["token"]}).json()["token"]
    res = dana.post(f"/api/games/{lobby['game']['id']}/lobby/deck", json={"text": "Commander\n1 Zephyr of the New Set (NWS) 7\nDeck\n10 Mountain\n"},
                    headers=h(seat))
    unresolved = next(s for s in res.json()["seats"] if s["id"] == "p2")["deck"]["report"]["unresolved"]
    assert [u.get("name") for u in unresolved] == ["Zephyr of the New Set"]


def test_rejected_card_data_is_named_with_the_reason(pod, monkeypatch):
    host, friend = pod
    to_host = TestClient(host.app, client=("192.168.1.20", 50000))
    bad = {**NEW, "colors": "not a list"}
    body = {"from": "DANA-PC", "port": 8000, "decks": [{"name": "X", "commanders": [NEW["name"]], "text": f"1 {NEW['name']}"}], "cards": [bad]}
    token = to_host.post("/api/lan/handoff", content=json.dumps(body), headers={"content-type": "application/json"}).json()["token"]
    lobby = host.post("/api/games", json={"mode": "lan", "lobby": True, "name": "Night", "players": [{"name": "Alice"}]}).json()
    seat = to_host.post("/api/join", json={"code": lobby["game"]["code"], "name": "Dana", "handoff": token}).json()["token"]
    brought = to_host.get(f"/api/games/{lobby['game']['id']}/lobby/brought", headers=h(seat)).json()
    assert brought["unknown"] == [{"name": "Zephyr of the New Set", "why": "its card data from DANA-PC couldn't be read"}]


def test_the_missing_lookup_is_for_the_network_only(pod):
    host, _ = pod
    lan = peer(host, ("192.168.1.20", 50000))
    ids = [NEW["id"], host.app.state.services.cards.resolve("Sol Ring")["id"]]
    res = lan.post("/api/lan/handoff/missing", json={"ids": ids})
    assert res.status_code == 200 and res.json() == {"missing": [NEW["id"]]}
    assert peer(host, ("8.8.8.8", 1)).post("/api/lan/handoff/missing", json={"ids": ids}).status_code == 403
    assert lan.post("/api/lan/handoff/missing", json={"ids": ["x"] * 20_001}).status_code == 422


# --------------------------------------------------------------------------- art over the LAN


def test_art_is_fetched_with_caps_and_only_real_jpegs(tmp_path, cards):
    from app.cards.images import ImageStore

    store = ImageStore(tmp_path / "img")
    krenko, sol = cards.resolve("Krenko, Mob Boss")["id"], cards.resolve("Sol Ring")["id"]
    delver = cards.resolve("Delver of Secrets")["id"]
    served: list[str] = []

    def handle(req: httpx.Request) -> httpx.Response:
        served.append(f"{req.url.path}?{req.url.query.decode()}")
        cid = req.url.path.rsplit("/", 1)[1]
        if cid == sol:
            return httpx.Response(200, content=b"<html>not an image</html>", headers={"content-type": "text/html"})
        return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})

    stored = lan_art.fetch_art("http://192.168.1.20:8000", cards, store, [krenko, sol, delver, krenko], transport=httpx.MockTransport(handle))
    assert set(stored) == {krenko, delver}
    assert store.has(krenko) and not store.has(sol) and store.has(delver, face=1)  # both faces of a double-faced card
    assert all(p.startswith("/api/images/") for p in served)
    served.clear()
    assert lan_art.fetch_art("http://192.168.1.20:8000", cards, store, [krenko], transport=httpx.MockTransport(handle)) == []
    assert served == []  # already here: nothing asked
    many = [f"{i:08x}-0000-4000-8000-000000000000" for i in range(lan_art.MAX_IMAGES + 50)]
    assert len(lan_art.wanted(cards, store, many)) <= lan_art.MAX_IMAGES


# --------------------------------------------------------------------------- the art keeper


@pytest.fixture()
def keeper_client(tmp_path, card_db, monkeypatch):
    calls: list[list[str]] = []
    outcome: dict[str, Any] = {"offline": False, "fail": 0}

    def fake_fetch(self, printing_ids, progress, *, tokens=True):
        if outcome["offline"]:
            raise httpx.ConnectError("no internet")
        calls.append(list(printing_ids))
        if "during" in outcome:
            outcome.pop("during")()
        failed = min(outcome["fail"], len(printing_ids))
        return SimpleNamespace(requested=len(printing_ids), downloaded=len(printing_ids) - failed, skipped=0, failed=failed)

    from app.services import Services

    monkeypatch.setattr(Services, "fetch_artwork", fake_fetch)
    settings = load_settings({"FYODOR_DATA_DIR": str(card_db.parent), "FYODOR_FRONTEND_DIST": str(tmp_path / "nodist")})
    with TestClient(create_app(settings)) as c:
        keeper: ArtKeeper = c.app.state.services.art_keeper
        keeper.synchronous = True  # tests run the work inline
        keeper.downloads = True
        yield c, keeper, calls, outcome


def test_saving_a_deck_keeps_its_art_for_offline_play(keeper_client):
    client, keeper, calls, _ = keeper_client
    res = client.post("/api/decks", json={"name": "Goblins", "text": "Commander\n1 Krenko, Mob Boss\nDeck\n1 Sol Ring\n"})
    assert res.status_code == 201
    assert len(calls) == 1 and len(calls[0]) == 3  # the deck's own printings and Krenko's Goblin token, quietly
    status = client.get("/api/decks/art-keeper").json()
    assert status["enabled"] is True and status["pending"] == 0


def test_a_deck_whose_art_came_only_in_part_is_tried_again(keeper_client):
    """One image timing out mustn't leave that card a text proxy for good: the deck stays on the list for the next try."""
    client, keeper, calls, outcome = keeper_client
    outcome["fail"] = 1
    client.post("/api/decks", json={"name": "Goblins", "text": "1 Krenko, Mob Boss\n1 Sol Ring\n"})
    assert len(calls) == 1 and client.get("/api/decks/art-keeper").json()["pending"] == 1
    outcome["fail"] = 0
    keeper.kick()
    assert len(calls) == 2 and client.get("/api/decks/art-keeper").json()["pending"] == 0


def test_decks_saved_while_the_keeper_works_join_the_same_pass(keeper_client):
    """Adding several precons saves them one after another while the first one's art downloads: none waits for the retry timer."""
    client, keeper, calls, outcome = keeper_client
    outcome["offline"] = True  # both decks wait on the list
    first = client.post("/api/decks", json={"name": "A", "text": "1 Sol Ring\n"}).json()["id"]
    second = client.post("/api/decks", json={"name": "B", "text": "1 Krenko, Mob Boss\n"}).json()["id"]
    outcome["offline"] = False
    keeper.pending = [first]
    outcome["during"] = lambda: keeper.pending.append(second)  # saved while the first deck's art downloads
    keeper.kick()
    assert len(calls) == 2 and keeper.pending == []


def test_offline_the_keeper_waits_and_retries_when_back_online(keeper_client):
    client, keeper, calls, outcome = keeper_client
    outcome["offline"] = True
    deck = client.post("/api/decks", json={"name": "Goblins", "text": "1 Krenko, Mob Boss\n"}).json()
    assert calls == [] and client.get("/api/decks/art-keeper").json()["pending"] == 1  # kept for later, no error shown
    assert json.loads(keeper.path.read_text())["pending"] == [deck["id"]]  # survives a restart
    outcome["offline"] = False
    keeper.kick()
    assert len(calls) == 1 and client.get("/api/decks/art-keeper").json()["pending"] == 0


def test_the_keeper_can_be_turned_off(keeper_client):
    client, keeper, calls, _ = keeper_client
    assert client.put("/api/decks/art-keeper", json={"enabled": False}).json()["enabled"] is False
    client.post("/api/decks", json={"name": "Goblins", "text": "1 Krenko, Mob Boss\n"})
    assert calls == []
    assert TestClient(client.app, client=("192.168.1.20", 1)).put("/api/decks/art-keeper", json={"enabled": True}).status_code == 403


def test_no_network_setting_means_no_downloads(tmp_path, card_db, monkeypatch):
    from app.services import Services

    monkeypatch.setattr(Services, "fetch_artwork", lambda self, ids, progress, tokens=True: pytest.fail("downloaded with network off"))
    settings = load_settings({"FYODOR_DATA_DIR": str(card_db.parent), "FYODOR_FRONTEND_DIST": str(tmp_path / "nodist"),
                              "FYODOR_ALLOW_NETWORK": "0"})
    with TestClient(create_app(settings)) as c:
        c.app.state.services.art_keeper.synchronous = True
        c.app.state.services.art_keeper.downloads = True
        c.post("/api/decks", json={"name": "Goblins", "text": "1 Krenko, Mob Boss\n"})


# --------------------------------------------------------------------------- asking from any server


def test_a_local_only_fyodor_still_finds_tables(tmp_path, monkeypatch):
    """The friend's own Fyodor may listen on 127.0.0.1 (--local): it doesn't answer, but asking works."""
    from app.multiplayer import discovery as D

    async def found(targets, *, timeout, exclude=None):
        return [{"id": "x", "name": "DESKTOP-42", "url": "http://192.168.1.7:8000", "version": "0.1.0", "tables": []}]

    monkeypatch.setattr(D, "query", found)
    settings = load_settings({"FYODOR_DATA_DIR": str(tmp_path / "d"), "FYODOR_FRONTEND_DIST": str(tmp_path / "nodist"), "FYODOR_HOST": "127.0.0.1"})
    with TestClient(create_app(settings)) as c:
        assert c.app.state.discovery.port is None
        assert [s["name"] for s in c.get("/api/lan/nearby").json()] == ["DESKTOP-42"]
