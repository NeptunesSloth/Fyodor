"""Turn clock (stage 3): the clock is saved with the game's extras, restored after a crash without charging the downtime, never refunded
by undo, fresh on a rematch, and carried back to the lobby."""

from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from app.api import night as night_api
from app.game.turn_clock import ClockSettings, TurnClock
from app.main import create_app
from app.multiplayer import turn_clock_driver as driver
from tests.conftest import claim_host, connect_game
from tests.test_recovery import crash
from tests.test_rules_effects import build, replay_matches
from tests.test_turn_clock_driver import ACTED_ALICE, seated
from tests.test_turn_clock_settings import started

DAMAGED = "The turn clock in this save couldn't be read, so it is off."


@pytest.fixture(autouse=True)
def _no_leftover_timers():
    yield
    for room_id in list(driver._drivers):
        driver.forget(room_id)


def room_of(client, gid):
    return client.app.state.services.hub.get(gid)


def notices(room) -> list[str]:
    return [p.t for e in room.session.notices for p in e.parts]


def save_and_load(client, gid, token):
    saved = client.post(f"/api/games/{gid}/save", json={"name": "Clocked"}, headers={"X-Seat-Token": token})
    assert saved.status_code == 201, saved.text
    loaded = client.post(f"/api/saves/{saved.json()['id']}/load", json={"mode": "lan"})
    assert loaded.status_code == 201, loaded.text
    return room_of(client, loaded.json()["game"]["id"])


def test_a_save_then_a_load_keeps_the_settings_and_the_banks(client) -> None:
    gid, alice, _ = started(client, clock={"on": True, "bank_seconds": 600, "at_zero": "show"})
    clock = room_of(client, gid).game.clock
    clock.banks.update({"p1": 412.5, "p2": 90.0})
    room = save_and_load(client, gid, alice)
    loaded = room.game.clock
    assert loaded is not None and loaded is not clock
    assert loaded.settings == ClockSettings.model_validate({"on": True, "bank_seconds": 600, "at_zero": "show"})
    for pid, bank in {"p1": 412.5, "p2": 90.0}.items():
        assert abs(loaded.bank(pid, driver.now()) - bank) <= 0.5


def test_a_save_without_a_clock_loads_without_one(client) -> None:
    gid, alice, _ = started(client)
    assert room_of(client, gid).game.clock is None
    room = save_and_load(client, gid, alice)
    assert room.game.clock is None
    assert DAMAGED not in notices(room)


def test_a_damaged_clock_loads_with_no_clock_and_a_notice(client) -> None:
    gid, _, _ = started(client, clock={"on": True})
    session = room_of(client, gid).game
    services = client.app.state.services
    saved = services.saves.save(session.state, session.history, name="Damaged",
                                extras={"table_snapshots": [], "clock": {"settings": {"on": True}, "banks": {"p1": -5}}})
    loaded = client.post(f"/api/saves/{saved['id']}/load", json={"mode": "lan"})
    assert loaded.status_code == 201, loaded.text
    room = room_of(client, loaded.json()["game"]["id"])
    assert room.game.clock is None
    assert DAMAGED in notices(room)


def test_a_crash_keeps_the_banks_and_charges_nobody_until_a_player_is_back(settings, card_db, monkeypatch) -> None:  # Review Focus 3
    offset = [0.0]
    monkeypatch.setattr(driver, "now", lambda: time.monotonic() + offset[0])
    first = TestClient(create_app(settings))  # no lifespan: no final autosave
    claim_host(first)
    gid, alice, bob = started(first, clock={"on": True, "bank_seconds": 60, "buffer_seconds": 5})
    room = room_of(first, gid)
    room.game.clock.banks["p1"] = 0.0
    first.app.state.services.autosave(room)  # the last checkpoint
    room.game.clock.banks["p2"] = 42.5
    first.app.state.services.hub.persist(room)  # a later change: only the crash record has it
    crash(first)

    with TestClient(create_app(settings)) as second:
        room = room_of(second, gid)
        clock = room.game.clock
        assert clock is not None and clock.settings.bank_seconds == 60
        offset[0] += 1000  # the server was down, then nobody has reconnected yet
        assert clock.bank("p1", driver.now()) == 0.0 and clock.bank("p2", driver.now()) == 42.5
        before = len(room.game.history.actions)
        with connect_game(second, gid, alice) as ws_a:
            ws_a.receive_json()
            offset[0] += 10  # Alice's buffer runs out; nobody acts
            with connect_game(second, gid, bob) as ws_b:
                ws_b.receive_json()
                for _ in range(300):
                    if len(room.game.history.actions) > before:
                        break
                    time.sleep(0.01)
        assert len(room.game.history.actions) > before
        assert room.game.history.actions[before].actor == "p1"
        assert ACTED_ALICE in notices(room)


def test_undo_never_refunds_the_clock(cards, monkeypatch) -> None:
    now = [1000.0]
    monkeypatch.setattr(driver, "now", lambda: now[0])
    s = build(cards)
    s.clock = TurnClock(settings=ClockSettings.model_validate({"on": True}))
    hub, room, _, _ = seated(s)
    s.clock.banks["p1"] = 0.0
    driver.poke(hub, room)
    now[0] += 30
    assert asyncio.run(driver.tick(hub, room)) == ["p1"]
    s.undo("p1", host=True)
    driver.poke(hub, room)
    assert s.clock.bank("p1", driver.now()) == 0.0
    replay_matches(s)


def test_a_rematch_has_full_banks_and_the_lobby_keeps_the_settings(client) -> None:
    gid, _, _ = started(client, clock={"on": True, "bank_seconds": 600, "buffer_seconds": 10})
    services = client.app.state.services
    room = room_of(client, gid)
    old = room.game.clock
    old.banks.update({"p1": 12.0, "p2": 300.0})
    night_api.rematch(services, room)
    fresh = room.game.clock
    assert fresh is not None and fresh is not old
    assert fresh.settings == old.settings
    assert all(fresh.bank(pid, driver.now()) == 600.0 for pid in ("p1", "p2"))
    night_api.to_lobby(services, room)
    assert room.lobby.clock == ClockSettings.model_validate({"on": True, "bank_seconds": 600, "buffer_seconds": 10})
