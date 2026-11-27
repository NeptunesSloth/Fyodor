"""Turn clock (stage 3): the lobby's setting and the host's table controls (POST /api/games/{id}/clock)."""

from __future__ import annotations

import pytest

from tests.test_lobby import ALICE_DECK, BOB_DECK, create_lobby, h

GRUUL = "Commander\n1 Krenko, Mob Boss\n\nMain\n20 Mountain\n"


def started(client, *, bot: bool = False, **extra):
    gid, code, alice = create_lobby(client, automation="full", turn_order="seats", **extra)
    bob = client.post("/api/join", json={"code": code, "name": "Bob"}).json()["token"]
    client.post(f"/api/games/{gid}/lobby/deck", json={"text": ALICE_DECK}, headers=h(alice))
    client.post(f"/api/games/{gid}/lobby/deck", json={"text": BOB_DECK}, headers=h(bob))
    if bot:
        deck_id = client.post("/api/decks", json={"text": GRUUL, "name": "Gruul"}).json()["id"]
        assert client.post(f"/api/games/{gid}/lobby/bot", json={"deck_id": deck_id}, headers=h(alice)).status_code == 200
    client.post(f"/api/games/{gid}/lobby/ready", json={"ready": True}, headers=h(alice))
    client.post(f"/api/games/{gid}/lobby/ready", json={"ready": True}, headers=h(bob))
    res = client.post(f"/api/games/{gid}/lobby/start", json={"first_player": 0, "force": True}, headers=h(alice))
    assert res.status_code == 200, res.text
    return gid, alice, bob


def room_of(client, gid):
    return client.app.state.services.hub.get(gid)


def clock(client, gid, token, **body):
    return client.post(f"/api/games/{gid}/clock", json=body, headers=h(token))


def notices(room) -> list[str]:
    return [e.parts[0].t for e in room.session.notices]


def test_a_lobby_with_the_clock_on_starts_with_a_bank_per_human_seat(client) -> None:
    gid, alice, _ = started(client, bot=True, clock={"on": True})
    room = room_of(client, gid)
    assert room.seats["p3"].bot
    c = room.game.clock
    assert c is not None and c.settings.on
    assert c.banks == {"p1": 1500.0, "p2": 1500.0}
    view = client.get(f"/api/games/{gid}/view", headers=h(alice)).json()
    assert view["game"]["clock"]["settings"]["on"] is True and "p3" not in view["game"]["clock"]["players"]


def test_the_lobby_clock_setting_changes_with_the_settings_and_a_sandbox_has_none(client) -> None:
    gid, _, _ = create_lobby(client, format="sandbox", clock={"on": True})
    assert room_of(client, gid).lobby.clock.on is False
    gid, _, alice = create_lobby(client)
    res = client.post(f"/api/games/{gid}/lobby/settings", json={"clock": {"on": True, "bank_seconds": 600}}, headers=h(alice))
    assert res.status_code == 200, res.text
    assert room_of(client, gid).lobby.clock.bank_seconds == 600
    res = client.post(f"/api/games/{gid}/lobby/settings", json={"format": "sandbox"}, headers=h(alice))
    assert res.status_code == 200 and room_of(client, gid).lobby.clock.on is False


def test_a_lobby_clock_out_of_range_or_with_an_unknown_field_is_422(client) -> None:
    gid, _, alice = create_lobby(client)
    for bad in ({"bank_seconds": 10}, {"nope": 1}):
        res = client.post(f"/api/games/{gid}/lobby/settings", json={"clock": bad}, headers=h(alice))
        assert res.status_code == 422, bad
    assert client.post("/api/games", json={"mode": "lan", "lobby": True, "clock": {"bank_seconds": 10}}).status_code == 422


def test_the_host_adds_time_and_it_is_logged(client) -> None:
    gid, alice, _ = started(client, clock={"on": True})
    res = clock(client, gid, alice, op="add_time", player="p2", seconds=300)
    assert res.status_code == 200, res.text
    room = room_of(client, gid)
    assert room.game.clock.banks["p2"] == 1800.0
    assert res.json()["view"]["game"]["clock"]["players"]["p2"]["bank"] == 1800.0
    assert "The host added 5:00 to Bob's clock." in notices(room)


def test_only_the_host_changes_the_clock(client) -> None:
    gid, alice, bob = started(client, clock={"on": True})
    room = room_of(client, gid)
    _, spectator = client.app.state.services.hub.claim_seat(room, name="Eve", seat=None, spectate=True)
    body = {"op": "add_time", "player": "p2", "seconds": 60}
    for token in (bob, spectator, "nonsense"):
        res = client.post(f"/api/games/{gid}/clock", json=body, headers=h(token))
        assert res.status_code == 403 and res.json()["detail"] == "Only the host can change the turn clock"
    assert client.post(f"/api/games/{gid}/clock", json=body).status_code == 403
    assert room.game.clock.banks["p2"] == 1500.0


def test_hot_seat_and_sandbox_tables_have_no_clock(client) -> None:
    a = client.post("/api/decks", json={"text": ALICE_DECK}).json()["id"]
    b = client.post("/api/decks", json={"text": BOB_DECK}).json()["id"]
    hot = client.post("/api/games", json={"name": "Hot", "mode": "local",
                                          "players": [{"name": "A", "deck_id": a}, {"name": "B", "deck_id": b}]})
    assert hot.status_code == 201, hot.text
    res = client.post(f"/api/games/{hot.json()['game']['id']}/clock", json={"op": "settings", "settings": {"on": True}})
    assert res.status_code == 409 and res.json()["detail"] == "The turn clock is for LAN tables"
    gid, alice, _ = started(client, format="sandbox")
    res = clock(client, gid, alice, op="settings", settings={"on": True})
    assert res.status_code == 409 and res.json()["detail"] == "A Sandbox table has no turn clock"


@pytest.mark.parametrize("body", [
    {"op": "add_time", "player": "p2", "seconds": 0},
    {"op": "add_time", "player": "p2", "seconds": 4000},
    {"op": "add_time", "player": "p9", "seconds": 60},
    {"op": "add_time", "player": "p2"},
    {"op": "add_time", "seconds": 60},
    {"op": "grace", "player": "p2"},
    {"op": "settings"},
    {"op": "settings", "settings": {"bank_seconds": 10}},
    {"op": "nope"},
    {"op": "grace", "player": "p2", "seconds": 60, "extra": 1},
])
def test_a_bad_request_is_422(client, body) -> None:
    gid, alice, _ = started(client, clock={"on": True})
    assert client.post(f"/api/games/{gid}/clock", json=body, headers=h(alice)).status_code == 422


def test_a_seat_that_is_not_a_human_player_is_422(client) -> None:
    gid, alice, _ = started(client, bot=True, clock={"on": True})
    for pid in ("p3", "p5"):
        res = clock(client, gid, alice, op="add_time", player=pid, seconds=60)
        assert res.status_code == 422 and res.json()["detail"] == "No such player"


def test_settings_turn_the_clock_on_off_and_change_it(client) -> None:
    gid, alice, _ = started(client)
    room = room_of(client, gid)
    assert room.game.clock is None
    res = clock(client, gid, alice, op="settings", settings={"on": True, "bank_seconds": 600})
    assert res.status_code == 200, res.text
    assert room.game.clock.settings.bank_seconds == 600 and "players" in res.json()["view"]["game"]["clock"]
    clock(client, gid, alice, op="add_time", player="p1", seconds=60)
    banks = dict(room.game.clock.banks)
    clock(client, gid, alice, op="settings", settings={"on": True, "bank_seconds": 900})
    assert room.game.clock.settings.bank_seconds == 900 and room.game.clock.banks == banks
    res = clock(client, gid, alice, op="settings", settings={"on": False})
    assert res.status_code == 200 and "players" not in res.json()["view"]["game"]["clock"]
    assert [t for t in notices(room) if t.startswith("The host") and "added" not in t] == [
        "The host turned the turn clock on.", "The host changed the turn clock settings.", "The host turned the turn clock off."]
    assert room.game.clock.banks == banks  # nothing is charged once it is off


def test_a_settings_change_charges_the_time_before_it(client, monkeypatch) -> None:  # review M3
    from app.multiplayer import turn_clock_driver as driver

    at = [1000.0]
    monkeypatch.setattr(driver, "now", lambda: at[0])
    gid, alice, _ = started(client, clock={"on": True})
    c = room_of(client, gid).game.clock
    c.sync({"p1": "x"}, {"p1"}, 1000.0)  # Alice is waited on
    at[0] = 1100.0                       # 100 s: the 30 s buffer, then 70 s of bank
    assert clock(client, gid, alice, op="settings", settings={"on": False}).status_code == 200
    assert c.banks["p1"] == 1430.0       # charged by the settings it ran under, not dropped


def test_more_time_to_reconnect_adds_to_the_budget_and_is_saved(client, monkeypatch) -> None:
    from app.multiplayer import turn_clock_driver as driver

    monkeypatch.setattr(driver, "now", lambda: 1000.0)
    gid, alice, _ = started(client, clock={"on": True, "grace_seconds": 30})
    room = room_of(client, gid)
    c = room.game.clock
    c.sync({"p2": "x"}, {"p1"}, 990.0)  # p2 is waited on and away: 10 of the 30 s spent by the request's instant
    assert c.next_event(990.0) == 1020.0
    res = clock(client, gid, alice, op="grace", player="p2", seconds=120)
    assert res.status_code == 200, res.text
    assert c.grace_left["p2"] == 140.0                  # 20 s left + exactly the 120 s given
    assert "The host gave Bob 2:00 more to reconnect." in notices(room)
    saves = []
    monkeypatch.setattr(client.app.state.services.hub, "persist", lambda r: saves.append(r.game.clock.dump(1000.0)))
    clock(client, gid, alice, op="grace", player="p2", seconds=60)
    assert saves and saves[-1]["grace_left"]["p2"] == 200.0  # (the budget is saved with the clock: persisted now)
