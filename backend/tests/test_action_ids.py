"""Action ids are scoped to the seat: a retried action applies once, and one seat's ids never touch another's."""

from __future__ import annotations

import sqlite3
import threading

from fastapi.testclient import TestClient

from app.main import create_app
from app.storage.app_db import MIGRATIONS
from app.storage.db import migrate
from app.storage.journal import MAX_CLIENT_ACTIONS, RoomJournal
from tests.conftest import claim_host, connect_game
from tests.test_protocol_privacy import P1_DECK, P2_DECK
from tests.test_recovery import act, h, lan_table


def hand(client, gid, token, seat):
    return len(client.get(f"/api/games/{gid}/view", headers=h(token)).json()["zones"][f"{seat}:hand"])


def log_len(client, gid, token):
    return len(client.get(f"/api/games/{gid}/view", headers=h(token)).json()["log"])


def ws_action(ws, msg_id, cid, action):
    ws.send_json({"type": "action", "id": msg_id, "client_action_id": cid, "action": action})
    for _ in range(20):  # state broadcasts may arrive around the answer
        r = ws.receive_json()
        if r.get("type") in ("ack", "error") and r.get("id") == msg_id:
            return r
    raise AssertionError("no answer")


# -- behaviour that already held before ids were seat-scoped -------------------------------------------


def test_rest_one_id_twice_draws_once_and_two_ids_draw_twice(client):
    gid, _, host, _ = lan_table(client)
    assert act(client, gid, host, {"type": "draw", "count": 1}, cid="draw-once-0001").json()["status"] == "ACCEPTED"
    assert act(client, gid, host, {"type": "draw", "count": 1}, cid="draw-once-0001").json()["status"] == "ALREADY_APPLIED"
    assert hand(client, gid, host, "p1") == 1
    assert act(client, gid, host, {"type": "draw", "count": 1}, cid="draw-once-0002").json()["status"] == "ACCEPTED"
    assert hand(client, gid, host, "p1") == 2


def test_socket_one_id_twice_draws_once_and_two_ids_draw_twice(client):
    gid, _, host, _ = lan_table(client)
    with connect_game(client, gid, host) as ws:
        ws.receive_json()
        draw = {"type": "draw", "count": 1}
        assert ws_action(ws, 1, "ws-draw-0001", draw)["status"] == "ACCEPTED"
        assert ws_action(ws, 2, "ws-draw-0001", draw) == {"type": "ack", "id": 2, "status": "ALREADY_APPLIED"}
        assert ws_action(ws, 3, "ws-draw-0002", draw)["status"] == "ACCEPTED"
    assert hand(client, gid, host, "p1") == 2


def test_a_rejected_action_retried_returns_the_same_rejection_and_logs_once(client):
    gid, _, host, _ = lan_table(client)
    bad = {"type": "tap", "card_ids": ["nope"]}
    first = act(client, gid, host, bad, cid="bad-action-0001")
    assert first.status_code in (404, 409, 422)
    logged = log_len(client, gid, host)
    again = act(client, gid, host, bad, cid="bad-action-0001")
    assert again.json()["status"] == "ALREADY_APPLIED" and again.json()["outcome"].startswith("REJECTED")
    assert log_len(client, gid, host) == logged
    with connect_game(client, gid, host) as ws:
        ws.receive_json()
        one = ws_action(ws, 1, "bad-ws-0001", bad)
        two = ws_action(ws, 2, "bad-ws-0001", bad)
        assert one["type"] == "error" and two["type"] == "error" and two["status"] == "REJECTED"
        assert two["message"] == one["message"]
    assert log_len(client, gid, host) == logged


# -- seat scoping --------------------------------------------------------------------------------------


def test_the_same_id_from_two_seats_applies_for_each_over_rest(client):
    gid, _, host, mike = lan_table(client)
    assert act(client, gid, host, {"type": "draw", "count": 1}, cid="shared-id-0001").json()["status"] == "ACCEPTED"
    res = act(client, gid, mike, {"type": "draw", "count": 1}, cid="shared-id-0001")
    assert res.status_code == 200 and res.json()["status"] == "ACCEPTED"
    assert hand(client, gid, host, "p1") == 1 and hand(client, gid, mike, "p2") == 1
    # each seat's own repeat is still a repeat
    assert act(client, gid, mike, {"type": "draw", "count": 1}, cid="shared-id-0001").json()["status"] == "ALREADY_APPLIED"
    assert hand(client, gid, mike, "p2") == 1


def test_the_same_id_from_two_seats_applies_for_each_over_the_socket(client):
    gid, _, host, mike = lan_table(client)
    draw = {"type": "draw", "count": 1}
    with connect_game(client, gid, host) as a, connect_game(client, gid, mike) as b:
        a.receive_json()
        b.receive_json()
        assert ws_action(a, 1, "shared-ws-0001", draw)["status"] == "ACCEPTED"
        assert ws_action(b, 1, "shared-ws-0001", draw)["status"] == "ACCEPTED"
        assert ws_action(b, 2, "shared-ws-0001", draw)["status"] == "ALREADY_APPLIED"
    assert hand(client, gid, host, "p1") == 1 and hand(client, gid, mike, "p2") == 1


def test_another_seat_reusing_an_id_is_answered_like_any_new_action(client):
    """Mike sends an id Jonathan used, then a never-used id for the same action: the answers match in everything but the numbers
    that change with the table (he learns nothing about Jonathan's outcome, accepted or rejected)."""
    gid, _, host, mike = lan_table(client)
    act(client, gid, host, {"type": "draw", "count": 1}, cid="probe-accepted-1")
    act(client, gid, host, {"type": "tap", "card_ids": ["nope"]}, cid="probe-rejected-1")
    for used, fresh in (("probe-accepted-1", "probe-fresh-0001"), ("probe-rejected-1", "probe-fresh-0002")):
        action = {"type": "draw", "count": 1}
        reused = act(client, gid, mike, action, cid=used)
        new = act(client, gid, mike, action, cid=fresh)
        assert reused.status_code == new.status_code == 200
        assert reused.json()["status"] == new.json()["status"] == "ACCEPTED"
        assert "outcome" not in reused.json() and "outcome" not in new.json()
        assert reused.json().keys() == new.json().keys()
    assert hand(client, gid, mike, "p2") == 4
    # a rejected action under a used id is rejected on its own merits, with the normal rejection
    bad = {"type": "tap", "card_ids": ["nope"]}
    act(client, gid, host, bad, cid="probe-rejected-2")
    one = act(client, gid, mike, bad, cid="probe-rejected-2")
    two = act(client, gid, mike, bad, cid="probe-fresh-0003")
    assert one.status_code == two.status_code and one.json() == two.json()
    act(client, gid, host, {"type": "draw", "count": 1}, cid="probe-ws-used-1")
    with connect_game(client, gid, mike) as ws:
        ws.receive_json()
        r1 = ws_action(ws, 1, "probe-ws-used-1", {"type": "draw", "count": 1})
        r2 = ws_action(ws, 2, "probe-fresh-0004", {"type": "draw", "count": 1})
        assert r1 == {**r2, "id": 1} and r1["status"] == "ACCEPTED"


def test_a_hot_seat_table_acting_as_another_seat_is_deduplicated_in_that_seats_space(client):
    """At a hot-seat table one browser plays every seat: the id counts per seat the action is performed as."""
    a = client.post("/api/decks", json={"text": P1_DECK}).json()["id"]
    b = client.post("/api/decks", json={"text": P2_DECK}).json()["id"]
    game = client.post("/api/games", json={"mode": "local", "players": [{"name": "A", "deck_id": a}, {"name": "B", "deck_id": b}]}).json()
    gid = game["game"]["id"]

    def as_seat(seat, cid):
        return client.post(f"/api/games/{gid}/actions", json={"action": {"type": "draw", "count": 1}, "as": seat, "client_action_id": cid})

    assert as_seat("p1", "hotseat-0001").json()["status"] == "ACCEPTED"
    assert as_seat("p2", "hotseat-0001").json()["status"] == "ACCEPTED"
    assert as_seat("p2", "hotseat-0001").json()["status"] == "ALREADY_APPLIED"
    assert as_seat("p1", "hotseat-0001").json()["status"] == "ALREADY_APPLIED"
    view = client.get(f"/api/games/{gid}/view").json()
    assert len(view["zones"]["p1:hand"]) == 1 and len(view["zones"]["p2:hand"]) == 1


def test_one_seat_flooding_ids_cannot_evict_another_seats_ids(client):
    gid, _, host, mike = lan_table(client)
    assert act(client, gid, mike, {"type": "draw", "count": 1}, cid="mike-pending-01").json()["status"] == "ACCEPTED"
    services = client.app.state.services
    room = services.hub.rooms[gid]
    for i in range(MAX_CLIENT_ACTIONS * 2):
        services.hub.remember_action(room, "p1", f"flood-{i:06d}", "ACCEPTED")
    assert len(room.client_actions["p1"]) <= MAX_CLIENT_ACTIONS  # the sender's own bound
    again = act(client, gid, mike, {"type": "draw", "count": 1}, cid="mike-pending-01")
    assert again.json()["status"] == "ALREADY_APPLIED"
    assert hand(client, gid, mike, "p2") == 1


def test_the_journal_prunes_one_seats_ids_and_only_that_seats(client):
    """The stored copy is bounded per seat too: after p1 floods, p1 has exactly the bound remembered and p2's pending id is still there."""
    gid, _, host, mike = lan_table(client)
    assert act(client, gid, mike, {"type": "draw", "count": 1}, cid="mike-pending-01").json()["status"] == "ACCEPTED"
    services = client.app.state.services
    room = services.hub.rooms[gid]
    for i in range(MAX_CLIENT_ACTIONS * 2):
        services.hub.remember_action(room, "p1", f"flood-{i:06d}", "ACCEPTED")
    stored = {r.game_id: r.client_actions for r in services.journal.live()}[gid]
    assert len(stored["p1"]) == MAX_CLIENT_ACTIONS
    assert f"flood-{MAX_CLIENT_ACTIONS * 2 - 1:06d}" in stored["p1"] and "flood-000000" not in stored["p1"]  # the newest are the ones kept
    assert "mike-pending-01" in stored["p2"]


def test_ids_survive_a_restart_per_seat(settings, card_db):
    first = TestClient(create_app(settings))
    claim_host(first)
    gid, _, host, mike = lan_table(first)
    assert act(first, gid, host, {"type": "draw", "count": 1}, cid="persist-0001").json()["status"] == "ACCEPTED"
    del first
    with TestClient(create_app(settings)) as second:
        claim_host(second)
        assert act(second, gid, host, {"type": "draw", "count": 1}, cid="persist-0001").json()["status"] == "ALREADY_APPLIED"
        res = act(second, gid, mike, {"type": "draw", "count": 1}, cid="persist-0001")
        assert res.json()["status"] == "ACCEPTED"


# -- old journals --------------------------------------------------------------------------------------


def test_a_journal_written_with_room_scoped_ids_still_loads(tmp_path):
    conn = sqlite3.connect(tmp_path / "old.sqlite")
    conn.row_factory = sqlite3.Row
    migrate(conn, MIGRATIONS[:13], name="app")  # the schema as it was before this change
    conn.execute("INSERT INTO live_rooms (game_id, meta, checkpoint, updated_at) VALUES ('g1', '{}', NULL, 1.0)")
    conn.execute("INSERT INTO client_actions (game_id, client_action_id, outcome, created_at) VALUES ('g1', 'old-room-id-01', 'ACCEPTED', 1.0)")
    conn.commit()
    migrate(conn, MIGRATIONS, name="app")
    journal = RoomJournal(conn, threading.RLock())
    live = journal.live()
    assert len(live) == 1 and live[0].game_id == "g1"
    # an old entry never answers a seat's lookup
    assert all("old-room-id-01" not in acts for acts in live[0].client_actions.values())
    journal.remember_action("g1", "p1", "new-id-0001", "ACCEPTED")
    again = journal.live()[0].client_actions
    assert again == {"p1": {"new-id-0001": "ACCEPTED"}}
    journal.remember_action("g1", "p2", "new-id-0001", "REJECTED: no")
    assert journal.live()[0].client_actions == {"p1": {"new-id-0001": "ACCEPTED"}, "p2": {"new-id-0001": "REJECTED: no"}}
