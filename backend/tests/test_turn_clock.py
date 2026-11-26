"""Turn clock (stage 3, task 1): who the engine waits on, and charging them a buffer then a bank on monotonic time."""

from __future__ import annotations

import json

from app.game.rules_state import Decision
from app.game.state import Pregame, PregameSeat
from app.game.turn_clock import MAX_BANK, MAX_GRACE_EXTRA, ClockSettings, TurnClock, waiting_on
from tests.test_rules_effects import build


def on(**kw):
    return TurnClock(settings=ClockSettings(on=True, **kw))


def test_buffer_first_then_bank():
    c = on()
    c.sync({"p1": "k"}, {"p1"}, 0.0)
    c.sync({"p1": "k"}, {"p1"}, 40.0)
    assert c.bank("p1", 40.0) == 1490.0 and "p2" not in c.banks          # nobody else was waited on


def test_same_key_keeps_its_buffer_new_key_refills():          # Review Focus 4
    c = on()
    c.sync({"p1": "k"}, {"p1"}, 0.0)
    c.hold(20.0)
    c.sync({"p1": "k"}, {"p1"}, 25.0)
    assert c.public(25.0, 0)["players"]["p1"]["buffer"] == 10.0
    c.sync({"p1": "k2"}, {"p1"}, 26.0)
    assert c.public(26.0, 0)["players"]["p1"]["buffer"] == 30.0


def test_held_and_exempt_are_not_charged():
    c = on()
    c.sync({"p1": "k"}, {"p1"}, 0.0)
    c.hold(1.0)
    c.sync({"p1": "k"}, {"p1"}, 500.0)
    assert c.bank("p1", 500.0) == 1500.0
    c.sync({"p1": "k"}, {"p2"}, 500.0)
    c.sync({"p1": "k"}, {"p2"}, 600.0)  # p1 away 100 s < 120 s grace
    assert c.bank("p1", 600.0) == 1500.0
    assert c.next_event(600.0) == 620.0                                       # the driver wakes at the grace end
    c.sync({"p1": "k"}, {"p2"}, 620.0)
    c.sync({"p1": "k"}, {"p2"}, 700.0)
    assert c.bank("p1", 700.0) < 1500.0                                       # past grace: charged


def test_nobody_connected_charges_nobody():
    c = on()
    c.sync({"p1": "k"}, set(), 0.0)
    c.sync({"p1": "k"}, set(), 9999.0)
    assert c.bank("p1", 9999.0) == 1500.0 and c.due(9999.0) == []


def test_zero_then_each_decision_gets_its_buffer():
    c = on()
    c.banks["p1"] = 0.0
    c.sync({"p1": "k"}, {"p1"}, 0.0)
    assert c.due(29.9) == [] and c.due(30.0) == ["p1"] and c.next_event(0.0) == 30.0
    c.sync({"p1": "k2"}, {"p1"}, 31.0)
    assert c.due(31.0) == [] and c.bank("p1", 31.0) == 0.0


def test_show_only_never_due_and_floor_is_zero():
    c = on(at_zero="show")
    c.banks["p1"] = 5.0
    c.sync({"p1": "k"}, {"p1"}, 0.0)
    assert c.due(1e6) == [] and c.bank("p1", 1e6) == 0.0


def test_add_time_and_grace_are_capped():
    c = on()
    assert c.add_time("p1", 99999, 0.0) == MAX_BANK
    c.sync({"p1": "k"}, set(), 0.0)
    c.extend_grace("p1", 99999)  # away from t=0
    assert c.next_event(0.0) == 120 + MAX_GRACE_EXTRA                      # its grace end (act mode, bank untouched)


def test_dump_load_round_trip_and_bad_data():
    c = on()
    c.banks = {"p1": 12.5}
    assert TurnClock.load(c.dump(0.0)).banks == {"p1": 12.5}
    assert TurnClock.load({"settings": {"on": True}, "banks": {"p1": -3}}) is None
    assert TurnClock.load({"settings": {"on": True, "evil": 1}, "banks": {}}) is None


def test_public_block_never_names_the_decision():
    c = on()
    c.sync({"p1": "d:secret-id"}, {"p1"}, 0.0)
    block = c.public(0.0, 1.0)
    assert "secret-id" not in json.dumps(block)
    assert set(block["players"]["p1"]) == {"bank", "buffer", "running", "away"}


def test_read_methods_do_not_change_state_and_give_up_stops_spinning():
    c = on()
    c.banks["p1"] = 0.0
    c.sync({"p1": "k"}, {"p1"}, 0.0)
    c.due(500.0)
    c.public(500.0, 0)
    c.next_event(500.0)
    assert c.banks["p1"] == 0.0 and c.public(0.0, 0)["players"]["p1"]["buffer"] == 30.0
    c.give_up("p1")
    assert c.due(500.0) == [] and c.next_event(500.0) is None
    c.sync({"p1": "k"}, {"p1"}, 501.0)
    assert c.due(501.0) == []  # the same key stays given up
    c.sync({"p1": "k2"}, {"p1"}, 502.0)
    c.sync({"p1": "k"}, {"p1"}, 503.0)  # a gone key is forgotten
    assert c.due(600.0) == ["p1"]


def test_off_clock_charges_nothing():
    c = TurnClock()
    c.sync({"p1": "k"}, {"p1"}, 0.0)
    c.sync({"p1": "k"}, {"p1"}, 100.0)
    assert c.bank("p1", 100.0) == 1500.0 and c.due(100.0) == [] and "players" not in c.public(100.0, 0)


def test_waiting_on(cards):
    s = build(cards)                                     # Alice holds priority in main 1
    assert list(waiting_on(s.state)) == ["p1"]
    key = waiting_on(s.state)["p1"]
    assert key.startswith("p:") and key.endswith(":0")   # 117.3: the key of this priority
    s.state.rules.paused = True
    assert waiting_on(s.state) == {}
    s.state.rules.paused = False
    s.state.rules.conceded.append("p1")
    assert "p1" not in waiting_on(s.state)


def test_waiting_on_decider_dummy_and_automation_off(cards):
    s = build(cards)
    s.state.rules.decision = Decision(id="d1", player="p1", kind="choose_one", prompt="x", decider="p2")   # 723.5: p2 decides for p1
    assert waiting_on(s.state) == {"p2": "d:d1"}
    s.state.rules.decision = None
    s.state.rules.priority = "p2"
    s.state.players["p2"].dummy = True  # a target dummy seat is never charged
    assert waiting_on(s.state) == {}
    s.state.players["p2"].dummy = False
    s.state.rules.priority = "p1"
    s.state.settings.automation = "off"
    assert waiting_on(s.state) == {}  # automation off charges nobody


def test_waiting_on_pregame_charges_every_undecided_seat(cards):
    s = build(cards)
    s.state.pregame = Pregame(seats={"p1": PregameSeat(status="deciding", mulligans=1), "p2": PregameSeat(status="kept")})
    assert waiting_on(s.state) == {"p1": "m:deciding:1"}
    s.state.pregame.seats["p2"] = PregameSeat(status="bottoming")
    assert waiting_on(s.state) == {"p1": "m:deciding:1", "p2": "m:bottoming:0"}
