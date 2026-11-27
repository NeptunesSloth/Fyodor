"""Turn clock (stage 3): a timeout and a player action never both apply. The room lock orders a click and the clock's tick (the second
one sees the table the first left), and a click sent from a view older than the clock's action for that player is refused (over REST and
the socket), so a late click can't apply on top of what the clock just did. A concession always goes through (104.3a)."""

from __future__ import annotations

import asyncio
import time

import pytest

from app.game.session import GameSession
from app.multiplayer import turn_clock_driver as driver
from tests.conftest import connect_game
from tests.test_lobby import h
from tests.test_rules_effects import build
from tests.test_turn_clock_driver import clocked, seated
from tests.test_turn_clock_settings import room_of, started

LATE = "The clock already acted for you. Look at the table and try again."
PASS = {"type": "pass_priority"}


@pytest.fixture()
def t(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(driver, "now", lambda: now[0])
    return now


@pytest.fixture(autouse=True)
def _no_leftover_timers():
    yield
    for room_id in list(driver._drivers):
        driver.forget(room_id)


def test_a_pass_being_worked_out_and_the_timeout_apply_once(cards, t, monkeypatch):
    s = clocked(build(cards))
    hub, room, _, _ = seated(s)
    s.clock.banks["p1"] = 0.0
    driver.poke(hub, room)
    t[0] += 30  # p1's buffer is spent: the clock is due
    prepare = GameSession.prepare

    def slow(self, *a, **k):
        time.sleep(0.2)  # the pass is still being worked out when the tick runs
        return prepare(self, *a, **k)

    monkeypatch.setattr(GameSession, "prepare", slow)

    async def click():
        async with room.lock:
            await hub.perform(room, "p1", PASS)

    async def go():
        return await asyncio.gather(click(), driver.tick(hub, room))

    before = len(s.history.actions)
    _, acted = asyncio.run(go())
    new = s.history.actions[before:]
    assert [(a.type, a.actor) for a in new] == [("pass_priority", "p1")]
    assert acted == [] and s.clock.acted_revision("p1") is None


def post(client, gid, token, action, **extra):
    return client.post(f"/api/games/{gid}/actions", json={"action": action, **extra}, headers=h(token))


def test_a_late_pass_is_refused_and_one_from_the_view_that_showed_the_clock_is_accepted(client, t):
    gid, alice, bob = started(client, clock={"on": True})
    with connect_game(client, gid, alice) as ws:
        ws.receive_json()
        gid, alice, room = _after_clock(client, gid, alice, bob, t)
        acted = room.game.clock.acted_revision("p1")
        before = len(room.game.history.actions)
        res = post(client, gid, alice, PASS, seen_revision=acted - 1, client_action_id="late-pass-0001")
        assert (res.status_code, res.json()["detail"]) == (409, LATE)
        assert len(room.game.history.actions) == before
        # the same id, retried, gets the same answer (even with a newer view): REST answers a remembered refusal as any (test_action_ids)
        res = post(client, gid, alice, PASS, seen_revision=acted, client_action_id="late-pass-0001")
        assert (res.json()["status"], res.json()["outcome"]) == ("ALREADY_APPLIED", f"REJECTED: {LATE}")
        assert len(room.game.history.actions) == before
        res = post(client, gid, alice, PASS, seen_revision=acted, client_action_id="late-pass-0002")
        assert res.status_code == 200 and res.json()["status"] == "ACCEPTED"
        assert [(a.type, a.actor) for a in room.game.history.actions[before:]] == [("pass_priority", "p1")]


def test_an_action_with_no_view_revision_is_accepted_as_before(client, t):
    gid, alice, bob = started(client, clock={"on": True})
    with connect_game(client, gid, alice) as ws:
        ws.receive_json()
        gid, alice, room = _after_clock(client, gid, alice, bob, t)
        assert post(client, gid, alice, PASS).status_code == 200


def test_a_concession_from_an_old_view_always_goes_through(client, t):
    gid, alice, bob = started(client, clock={"on": True})
    with connect_game(client, gid, alice) as ws:
        ws.receive_json()
        gid, alice, room = _after_clock(client, gid, alice, bob, t)
        res = post(client, gid, alice, {"type": "concede"}, seen_revision=0)
        assert res.status_code == 200, res.text
        assert "p1" in room.game.state.rules.conceded


def test_a_late_pass_over_the_socket_is_rejected_with_the_message(client, t):
    gid, alice, bob = started(client, clock={"on": True})
    with connect_game(client, gid, alice) as ws:
        ws.receive_json()
        gid, alice, room = _after_clock(client, gid, alice, bob, t)
        acted = room.game.clock.acted_revision("p1")
        before = len(room.game.history.actions)
        ws.send_json({"type": "action", "id": 7, "client_action_id": "ws-late-0001", "action": PASS, "seen_revision": acted - 1})
        assert answer(ws, 7) == {"type": "error", "id": 7, "status": "REJECTED", "message": LATE}
        ws.send_json({"type": "action", "id": 8, "client_action_id": "ws-late-0001", "action": PASS, "seen_revision": acted})
        assert answer(ws, 8) == {"type": "error", "id": 8, "status": "REJECTED", "message": LATE}
        assert len(room.game.history.actions) == before
        ws.send_json({"type": "action", "id": 9, "client_action_id": "ws-late-0002", "action": PASS, "seen_revision": acted})
        assert answer(ws, 9) == {"type": "ack", "id": 9, "status": "ACCEPTED"}


def answer(ws, msg_id):
    for _ in range(30):  # state broadcasts may arrive around the answer
        r = ws.receive_json()
        if r.get("type") in ("ack", "error") and r.get("id") == msg_id:
            return r
    raise AssertionError("no answer")


def _after_clock(client, gid, alice, bob, t):
    """At p1's opening-hand choice the clock acts for p1 (p1's socket is open), then Bob answers his own: p1 has priority in the first
    main phase."""
    room = room_of(client, gid)
    for token in (alice, bob):
        assert post(client, gid, token, {"type": "mulligan_keep"}).status_code == 200
    room.game.clock.banks["p1"] = 0.0
    t[0] += 31
    assert client.portal.call(driver.tick, client.app.state.services.hub, room) in (["p1"], [])  # (or its own timer got there first)
    assert room.game.clock.acted_revision("p1") == room.revision  # the broadcast that showed the clock's action
    decision = room.game.state.rules.decision
    assert decision is not None and decision.player == "p2"
    assert post(client, gid, bob, {"type": "choose", "decision_id": decision.id, "option_ids": []}).status_code == 200
    assert room.game.state.rules.priority == "p1"
    return gid, alice, room


def test_seen_revision_is_bounded(client):
    gid, alice, _ = started(client)
    assert post(client, gid, alice, PASS, seen_revision=-1).status_code == 422
    assert post(client, gid, alice, PASS, seen_revision=2**31).status_code == 422
