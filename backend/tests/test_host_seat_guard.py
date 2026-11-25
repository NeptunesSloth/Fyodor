"""The host's own seat can't be removed, and a seat whose player left can't be claimed (security review F1)."""

from __future__ import annotations

import pytest

from tests.conftest import guest
from tests.test_protocol_privacy import P1_DECK, P2_DECK


@pytest.fixture()
def table(client):
    """A two-seat LAN table: the host in p1, Mike in p2."""
    a = client.post("/api/decks", json={"text": P1_DECK}).json()["id"]
    b = client.post("/api/decks", json={"text": P2_DECK}).json()["id"]
    game = client.post("/api/games", json={
        "mode": "lan", "players": [{"name": "Jonathan", "deck_id": a}, {"name": "Mike", "deck_id": b}],
    }).json()
    gid, code = game["game"]["id"], game["game"]["code"]
    host = game["seat"]["token"]
    mike = client.post("/api/join", json={"code": code, "name": "Mike"}, headers=guest(client)).json()["token"]
    return client, gid, code, host, mike


def remove(client, gid, token, pid):
    return client.post(f"/api/games/{gid}/actions", json={"action": {"type": "remove_player", "player": pid}},
                       headers={"X-Seat-Token": token})


def test_host_cannot_remove_their_own_seat(table):
    client, gid, _code, host, _mike = table
    room = client.app.state.services.hub.get(gid)
    assert room.host_seat == "p1"
    res = remove(client, gid, host, "p1")
    assert res.status_code == 409
    assert res.json()["detail"] == "The host's own seat can't be removed"
    assert room.seats["p1"].token == host
    assert not room.session.state.players["p1"].left


def test_a_left_seat_cannot_be_claimed(table):
    client, gid, code, host, _mike = table
    assert remove(client, gid, host, "p2").status_code == 200
    res = client.post("/api/join", json={"code": code, "name": "X", "seat": "p2"}, headers=guest(client))
    assert res.status_code == 409
    assert res.json()["detail"] == "That player has left the table"
    assert client.app.state.services.hub.get(gid).seats["p2"].token is None


def test_join_without_a_seat_skips_left_seats(table):
    client, gid, code, host, _mike = table
    assert remove(client, gid, host, "p2").status_code == 200
    res = client.post("/api/join", json={"code": code, "name": "X"}, headers=guest(client))
    assert res.status_code == 409
    assert res.json()["detail"] == "The table is full — join as a spectator"


def test_the_exploit_from_the_review_fails(table):
    client, gid, code, host, _mike = table
    room = client.app.state.services.hub.get(gid)
    assert remove(client, gid, host, "p1").status_code == 409
    res = client.post("/api/join", json={"code": code, "name": "X", "seat": "p1"}, headers=guest(client))
    assert res.status_code == 409  # p1 is still the host's
    stranger = res.json().get("token", "")
    assert not room.is_host(stranger)
    assert room.is_host(host)
