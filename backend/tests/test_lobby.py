"""LAN pregame lobby: seats, self-service deck choice, readiness, host controls, privacy."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

ALICE_DECK = """Commander
1x Atraxa, Praetors' Voice (2x2) 190
Deck
1x Counterspell (cmm) 81
1x Swords to Plowshares (sta) 10
10x Island (cmm) 1001
"""
BOB_DECK = """Commander
1x Krenko, Mob Boss (ddn) 13
Deck
12x Mountain (cmm) 1003
1x Lightning Bolt (clb) 187
"""


def create_lobby(client: TestClient, **extra) -> tuple[str, str, str]:
    res = client.post("/api/games", json={"mode": "lan", "lobby": True, "name": "Friday", "seats": 4,
                                           "players": [{"name": "Alice"}], **extra})
    assert res.status_code == 201, res.text
    body = res.json()
    return body["game"]["id"], body["game"]["code"], body["seat"]["token"]


def h(token: str) -> dict[str, str]:
    return {"X-Seat-Token": token}


@pytest.fixture()
def lobby(client):
    gid, code, alice = create_lobby(client)
    bob = client.post("/api/join", json={"code": code, "name": "Bob"}).json()["token"]
    return client, gid, code, alice, bob


def lobby_of(client, gid, token):
    res = client.get(f"/api/games/{gid}/lobby", headers=h(token))
    assert res.status_code == 200, res.text
    return res.json()


def seat(lobby_view, pid):
    return next(s for s in lobby_view["seats"] if s["id"] == pid)


def test_players_join_choose_their_own_decks_and_get_ready(lobby):
    client, gid, code, alice, bob = lobby
    view = lobby_of(client, gid, bob)
    assert view["phase"] == "lobby" and view["viewer"] == "p2" and not view["is_host"]
    assert [s["name"] for s in view["seats"][:2]] == ["Alice", "Bob"]
    assert lobby_of(client, gid, alice)["is_host"]

    # the game itself doesn't exist yet
    assert client.get(f"/api/games/{gid}/view", headers=h(bob)).status_code == 409
    act = client.post(f"/api/games/{gid}/actions", json={"action": {"type": "draw"}}, headers=h(bob))
    assert act.status_code == 409 and act.json()["code"] == "lobby"

    assert client.post(f"/api/games/{gid}/lobby/ready", json={"ready": True}, headers=h(bob)).status_code == 409
    res = client.post(f"/api/games/{gid}/lobby/deck", json={"text": BOB_DECK, "name": "Goblins"}, headers=h(bob))
    assert res.status_code == 200, res.text
    mine = seat(res.json(), "p2")["deck"]
    assert mine["name"] == "Goblins" and mine["commanders"] == ["Krenko, Mob Boss"] and mine["card_count"] == 14
    assert mine["color_identity"] == ["R"] and mine["report"]["unresolved"] == []
    assert {"section": "main", "quantity": 12, "name": "Mountain"} in mine["list"]

    start = client.post(f"/api/games/{gid}/lobby/start", json={}, headers=h(alice))
    assert start.status_code == 409 and "Alice hasn't chosen a deck" in start.json()["detail"]
    assert client.post(f"/api/games/{gid}/lobby/start", json={}, headers=h(bob)).status_code == 403  # not host

    client.post(f"/api/games/{gid}/lobby/deck", json={"text": ALICE_DECK}, headers=h(alice))
    client.post(f"/api/games/{gid}/lobby/ready", json={"ready": True}, headers=h(alice))
    client.post(f"/api/games/{gid}/lobby/ready", json={"ready": True}, headers=h(bob))
    assert lobby_of(client, gid, alice)["start_blockers"] == []
    res = client.post(f"/api/games/{gid}/lobby/start", json={"first_player": 0}, headers=h(alice))
    assert res.status_code == 200, res.text
    assert res.json()["game"]["phase"] == "playing" and res.json()["game"]["id"] == gid

    # the same tokens now play the game; each player has the deck they chose
    state = client.app.state.services.hub.get(gid).session.state
    assert [state.players[p].name for p in state.seat_order] == ["Alice", "Bob"]
    assert state.players["p2"].deck_name == "Goblins"
    # opening hands are dealt under the table's mulligan rule (Commander London by default)
    assert len(state.zones["p2:hand"]) == 7 and len(state.zones["p2:library"]) == 6
    assert len(state.zones["p1:hand"]) == 7 and len(state.zones["p1:library"]) == 5
    assert state.settings.mulligan is not None and state.settings.mulligan.id == "commander_london"
    bob_view = client.get(f"/api/games/{gid}/view", headers=h(bob)).json()
    assert bob_view["viewer"] == "p2" and bob_view["game"]["settings"]["deck_privacy"] == "commander_only"
    assert "deck_id" not in bob_view["players"][0]
    assert bob_view["pregame"]["seats"]["p2"]["status"] == "deciding"
    assert client.post(f"/api/games/{gid}/actions", json={"action": {"type": "draw"}}, headers=h(bob)).status_code == 200


@pytest.mark.parametrize("privacy", ["private", "commander_only", "public"])
def test_deck_privacy_controls_what_others_learn(client, privacy):
    gid, code, alice = create_lobby(client, deck_privacy=privacy)
    bob = client.post("/api/join", json={"code": code, "name": "Bob"}).json()["token"]
    spec = client.post("/api/join", json={"code": code, "spectate": True}).json()["token"]
    client.post(f"/api/games/{gid}/lobby/deck", json={"text": BOB_DECK, "name": "Goblins"}, headers=h(bob))
    for token in (alice, spec):
        view = lobby_of(client, gid, token)
        deck = seat(view, "p2")["deck"]
        text = json.dumps(view)
        assert deck["card_count"] == 14
        assert "report" not in deck
        if privacy == "private":
            assert set(deck) == {"card_count"}
            assert "Krenko" not in text and "Goblins" not in text and "Mountain" not in text
        elif privacy == "commander_only":
            assert deck["commanders"] == ["Krenko, Mob Boss"] and deck["name"] == "Goblins"
            assert "list" not in deck and "Lightning Bolt" not in text
            # automation coverage: counts per level only (every card counted, nothing named)
            assert set(deck["coverage"]) == {"FULL", "PARTIAL", "REVIEW", "MANUAL"} and sum(deck["coverage"].values()) == 14
        else:
            assert {"section": "main", "quantity": 1, "name": "Lightning Bolt"} in deck["list"]
    # the owner always sees their own list
    assert "list" in seat(lobby_of(client, gid, bob), "p2")["deck"]

    client.post(f"/api/games/{gid}/lobby/deck", json={"text": ALICE_DECK, "name": "Superfriends"}, headers=h(alice))
    client.post(f"/api/games/{gid}/lobby/start", json={"force": True}, headers=h(alice))
    view = client.get(f"/api/games/{gid}/view", headers=h(alice)).json()
    bob_player = next(p for p in view["players"] if p["name"] == "Bob")
    assert ("deck_name" in bob_player) == (privacy != "private")


def test_host_kicks_moves_and_configures(lobby):
    client, gid, code, alice, bob = lobby
    # seat change
    res = client.post(f"/api/games/{gid}/lobby/seat", json={"seat": "p4"}, headers=h(bob))
    assert res.status_code == 200 and seat(res.json(), "p4")["name"] == "Bob" and not seat(res.json(), "p2")["claimed"]
    assert client.post(f"/api/games/{gid}/lobby/seat", json={"seat": "p1"}, headers=h(bob)).status_code == 409
    # can't shrink the table under a seated player
    assert client.post(f"/api/games/{gid}/lobby/settings", json={"seats": 2}, headers=h(alice)).status_code == 409
    # non-hosts can't change settings or kick
    assert client.post(f"/api/games/{gid}/lobby/settings", json={"seats": 5}, headers=h(bob)).status_code == 403
    assert client.post(f"/api/games/{gid}/lobby/kick", json={"seat": "p1"}, headers=h(bob)).status_code == 403
    # settings changes that affect the game un-ready everyone
    client.post(f"/api/games/{gid}/lobby/deck", json={"text": BOB_DECK}, headers=h(bob))
    client.post(f"/api/games/{gid}/lobby/ready", json={"ready": True}, headers=h(bob))
    res = client.post(f"/api/games/{gid}/lobby/settings", json={"deck_privacy": "public", "seats": 5}, headers=h(alice))
    assert res.status_code == 200
    assert res.json()["settings"]["deck_privacy"] == "public" and len(res.json()["seats"]) == 5
    assert not seat(res.json(), "p4")["ready"]
    # kick: the token stops working and the seat is free again
    assert client.post(f"/api/games/{gid}/lobby/kick", json={"seat": "p1"}, headers=h(alice)).status_code == 409
    res = client.post(f"/api/games/{gid}/lobby/kick", json={"seat": "p4"}, headers=h(alice))
    assert res.status_code == 200 and not seat(res.json(), "p4")["claimed"] and seat(res.json(), "p4")["deck"] is None
    assert client.get(f"/api/games/{gid}/lobby", headers=h(bob)).status_code == 403
    carol = client.post("/api/join", json={"code": code, "name": "Carol"}).json()
    assert carol["viewer"] == "p2"


def test_empty_seats_are_dropped_at_start_and_players_renumbered(client):
    gid, code, alice = create_lobby(client)
    bob = client.post("/api/join", json={"code": code, "name": "Bob", "seat": "p3"}).json()["token"]
    client.post(f"/api/games/{gid}/lobby/deck", json={"text": BOB_DECK}, headers=h(bob))
    assert client.post(f"/api/games/{gid}/lobby/start", json={}, headers=h(alice)).status_code == 409
    res = client.post(f"/api/games/{gid}/lobby/start", json={"force": True}, headers=h(alice))
    assert res.status_code == 200
    state = client.app.state.services.hub.get(gid).session.state
    assert state.seat_order == ["p1", "p2"] and state.players["p2"].name == "Bob"
    assert client.get(f"/api/games/{gid}/view", headers=h(bob)).json()["viewer"] == "p2"
    assert client.post(f"/api/games/{gid}/lobby/ready", json={}, headers=h(bob)).status_code == 409  # started


def test_decks_are_content_only_and_bounded(lobby):
    client, gid, code, alice, bob = lobby
    for body in ({}, {"text": "   "}, {"text": "../../etc/passwd"}, {"path": "/etc/passwd"}):
        res = client.post(f"/api/games/{gid}/lobby/deck", json=body, headers=h(bob))
        assert res.status_code in (413, 422), (body, res.text)
    huge = "Deck\n1x Island (cmm) 1001\n" + "\n".join(f"1x Card Number {i}" for i in range(450))
    assert client.post(f"/api/games/{gid}/lobby/deck", json={"text": huge}, headers=h(bob)).status_code == 413
    many = "Deck\n700x Mountain (cmm) 1003\n"
    assert client.post(f"/api/games/{gid}/lobby/deck", json={"text": many}, headers=h(bob)).status_code == 413
    # the host's library is reachable only from the host computer
    deck_id = client.post("/api/decks", json={"text": ALICE_DECK}).json()["id"]
    assert client.post(f"/api/games/{gid}/lobby/deck", json={"deck_id": deck_id}, headers=h(alice)).status_code == 200
    remote = TestClient(client.app, client=("192.168.1.20", 50000))
    res = remote.post(f"/api/games/{gid}/lobby/deck", json={"deck_id": deck_id}, headers=h(bob))
    assert res.status_code == 403
    assert remote.get("/api/decks").status_code == 403
    assert remote.get(f"/api/decks/{deck_id}").status_code == 403
    assert remote.get(f"/api/games/{gid}/lobby", headers=h(bob)).status_code == 200


def test_websocket_receives_lobby_then_game(lobby):
    client, gid, code, alice, bob = lobby
    with client.websocket_connect(f"/ws/games/{gid}?token={bob}") as ws:
        first = ws.receive_json()
        assert first["type"] == "lobby" and first["lobby"]["viewer"] == "p2"
        assert ws.receive_json()["type"] == "lobby"  # presence update after connecting
        ws.send_json({"type": "action", "action": {"type": "draw"}, "id": 1})
        assert ws.receive_json()["type"] == "error"
        client.post(f"/api/games/{gid}/lobby/deck", json={"text": BOB_DECK}, headers=h(bob))
        msg = ws.receive_json()
        assert msg["type"] == "lobby" and seat(msg["lobby"], "p2")["deck"]["commanders"] == ["Krenko, Mob Boss"]
        client.post(f"/api/games/{gid}/lobby/start", json={"force": True}, headers=h(alice))
        msg = ws.receive_json()
        assert msg["type"] == "state" and msg["view"]["viewer"] == "p2"
        # the game view never carries anyone's hidden cards
        state = client.app.state.services.hub.get(gid).session.state
        text = json.dumps(msg["view"])
        for cid in state.zones["p1:library"]:
            assert cid not in text


def test_deck_checks_are_advisory_and_private(lobby):
    client, gid, code, alice, bob = lobby
    client.post(f"/api/games/{gid}/lobby/settings", json={"deck_privacy": "commander_only"}, headers=h(alice))
    # 14 cards and four Mountains-plus-Bolt: not a legal Commander deck
    client.post(f"/api/games/{gid}/lobby/deck", json={"text": BOB_DECK + "2x Lightning Bolt (clb) 187\n"}, headers=h(bob))
    mine = seat(lobby_of(client, gid, bob), "p2")["deck"]
    messages = [w["message"] for w in mine["warnings"]]
    assert any("100" in m for m in messages) and any("Lightning Bolt" in m and "singleton" in m for m in messages)
    assert mine["warning_count"] == len([w for w in mine["warnings"] if w["level"] != "info"])
    theirs = seat(lobby_of(client, gid, alice), "p2")["deck"]
    assert theirs["warning_count"] == mine["warning_count"] and "warnings" not in theirs
    assert "Lightning Bolt" not in json.dumps(lobby_of(client, gid, alice))
    # "play anyway": readying and starting are never blocked by deck checks
    client.post(f"/api/games/{gid}/lobby/deck", json={"text": ALICE_DECK}, headers=h(alice))
    for t in (alice, bob):
        assert client.post(f"/api/games/{gid}/lobby/ready", json={"ready": True}, headers=h(t)).status_code == 200
    assert lobby_of(client, gid, alice)["start_blockers"] == []
    # Fyodor plays Commander only: the host can't switch the table to another format
    assert client.post(f"/api/games/{gid}/lobby/settings", json={"format": "sandbox"}, headers=h(alice)).status_code == 422
    for t in (alice, bob):  # changing table settings asks everyone to confirm again
        client.post(f"/api/games/{gid}/lobby/ready", json={"ready": True}, headers=h(t))
    assert client.post(f"/api/games/{gid}/lobby/start", json={}, headers=h(alice)).status_code == 200


def test_lobby_views_carry_an_increasing_revision(lobby):
    """Browsers get lobby updates over HTTP and WebSocket in any order; the revision orders them."""
    client, gid, code, alice, bob = lobby
    r0 = lobby_of(client, gid, alice)["revision"]
    after_deck = client.post(f"/api/games/{gid}/lobby/deck", json={"text": BOB_DECK}, headers=h(bob)).json()["revision"]
    after_ready = client.post(f"/api/games/{gid}/lobby/ready", json={"ready": True}, headers=h(bob)).json()["revision"]
    assert r0 < after_deck < after_ready
    assert lobby_of(client, gid, alice)["revision"] == after_ready  # reading doesn't bump it
