"""Turn clock (stage 3, task 1): who the engine waits on, and charging them a buffer then a bank on monotonic time."""

from __future__ import annotations

import json

import pytest

from app.game.errors import ActionError
from app.game.rules_state import Decision
from app.game.state import Pregame, PregameSeat
from app.game.turn_clock import MAX_BANK, MAX_GRACE_EXTRA, ClockSettings, TurnClock, waiting_on
from tests.game_helpers import act
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
    c.sync({"p1": "k"}, {"p2"}, 0.0)
    c.extend_grace("p1", 99999, 0.0)  # away from t=0
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


def test_top_level_extra_key_and_too_many_banks_are_rejected():
    assert TurnClock.load({"settings": {"on": True}, "banks": {}, "evil": 1}) is None
    assert TurnClock.load({"settings": {"on": True}, "banks": {f"p{i}": 1.0 for i in range(13)}}) is None
    assert TurnClock.load({"settings": {"on": True}, "banks": {f"p{i}": 1.0 for i in range(12)}}) is not None


def test_negative_time_is_refused():
    c = on()
    with pytest.raises(ValueError):
        c.add_time("p1", -5, 0.0)
    with pytest.raises(ValueError):
        c.extend_grace("p1", -5, 0.0)
    assert c.banks == {} and TurnClock.load(c.dump(0.0)) is not None


def test_due_and_next_event_agree_at_the_exact_boundary():
    c = on(buffer_seconds=5)
    c.banks["p1"] = 0.1
    c.sync({"p1": "k"}, {"p1"}, 0.3)
    t = c.next_event(0.3)
    assert t is not None and c.due(t) == ["p1"]
    assert c.due(t - 0.001) == []


def test_mark_acted_round_trip():
    c = on()
    assert c.acted_revision("p1") is None
    c.mark_acted("p1", 7)
    assert c.acted_revision("p1") == 7 and c.acted_revision("p2") is None


# -- the reconnect grace is a budget per player per game (final fix I1 + security Medium) -------------------------------------------


def test_drop_reconnect_drop_spends_one_budget_and_the_clock_comes_due():  # the security review's reproduction
    c = on(bank_seconds=60, buffer_seconds=5, grace_seconds=30)
    t, due_at = 0.0, None
    for _ in range(200):
        c.sync({"p1": "d:x"}, {"p2"}, t)          # p1 drops
        ev = c.next_event(t)
        if ev is not None and ev < t + 29:
            c.sync({"p1": "d:x"}, {"p2"}, ev)     # (the timer's wake at the end of the budget, as the driver does)
            if c.due(ev):
                due_at = ev
                break
        t += 29
        c.sync({"p1": "d:x"}, {"p1", "p2"}, t)    # â€¦ and is back for a moment
        if c.due(t) or c.due(t + 0.05):
            due_at = t
            break
        t += 0.05
    # 30 s of reconnect grace in all, then the 5 s buffer and the 60 s bank: due on the fourth return, not never
    assert due_at is not None and due_at <= 30 + 5 + 60 + 29
    assert c.bank("p1", t) == 0.0


def test_an_absent_players_next_decision_gets_no_fresh_grace():  # the final review's I1 reproduction
    c = on(bank_seconds=60)
    c.sync({"p1": "k1"}, {"p2"}, 0.0)                       # away from t=0, waited on
    assert c.next_event(0.0) == 120.0                        # the end of the reconnect grace
    c.sync({"p1": "k1"}, {"p2"}, 120.0)                      # (the timer's wake at the grace end)
    assert c.due(209.9) == [] and c.due(210.0) == ["p1"]     # 120 s grace, 30 s buffer, 60 s bank
    c.sync({"p2": "k2"}, {"p2"}, 210.0)                      # the clock acted: the wait moves on
    c.sync({"p1": "k3"}, {"p2"}, 212.0)                      # p1, still away, is waited on again
    assert c.next_event(212.0) == 242.0                      # only the buffer: no new grace
    assert c.public(212.0, 0)["players"]["p1"]["running"] is True


def test_a_host_extension_adds_exactly_its_seconds():
    c = on()
    c.sync({"p1": "k"}, {"p2"}, 0.0)
    c.sync({"p1": "k"}, {"p2"}, 100.0)                       # 100 of the 120 s spent
    c.extend_grace("p1", 60, 100.0)
    assert c.next_event(100.0) == 180.0                      # 20 s left + 60
    assert c.dump(100.0)["grace_left"] == {"p1": 80.0}


def test_reconnecting_does_not_refill_the_budget():
    c = on()
    c.sync({"p1": "k"}, {"p2"}, 0.0)
    c.sync({"p1": "k"}, {"p1", "p2"}, 100.0)                 # back after 100 s
    c.sync({"p1": "k2"}, {"p1", "p2"}, 150.0)                # a new decision, connected: charged, no grace touched
    c.sync({"p1": "k2"}, {"p2"}, 160.0)                      # drops again
    assert c.next_event(160.0) == 180.0                      # 20 s left of the budget, not 120
    assert c.public(160.0, 0)["players"]["p1"]["away"] is True


def test_the_budget_is_not_spent_while_held_nobody_is_here_or_not_waited_on():
    c = on()
    c.sync({"p1": "k"}, {"p2"}, 0.0)
    c.hold(10.0)                                             # 10 s spent; an action being worked out spends nothing
    c.sync({"p2": "k2"}, {"p2"}, 50.0)                       # not waited on: nothing spent
    c.sync({"p2": "k2"}, set(), 60.0)
    c.sync({"p1": "k3"}, set(), 100.0)                       # nobody connected: nothing spent
    c.sync({"p1": "k3"}, {"p2"}, 400.0)
    assert c.next_event(400.0) == 510.0                      # 110 s left


def test_save_and_load_keep_the_remaining_budget():
    c = on()
    c.sync({"p1": "k"}, {"p2"}, 0.0)
    saved = json.loads(json.dumps(c.dump(50.0)))             # 50 s spent, still away (projected into the save)
    assert saved["grace_left"] == {"p1": 70.0}
    back = TurnClock.load(saved)
    assert back is not None
    back.sync({"p1": "k"}, {"p2"}, 1000.0)
    assert back.next_event(1000.0) == 1070.0
    old = TurnClock.load({"settings": {"on": True}, "banks": {"p1": 12.0}})  # a save from before the budget: full
    assert old is not None and old.grace_left == {}
    old.sync({"p1": "k"}, {"p2"}, 0.0)
    assert old.next_event(0.0) == 120.0
    for bad in ({"p1": -1.0}, {"p1": float("nan")}, {"p1": 1e9}, {f"p{i}": 1.0 for i in range(13)}):
        assert TurnClock.load({"settings": {"on": True}, "banks": {}, "grace_left": bad}) is None


def test_turning_the_clock_off_keeps_the_budget():
    c = on()
    c.sync({"p1": "k"}, {"p2"}, 0.0)
    c.sync({"p1": "k"}, {"p2"}, 100.0)
    c.settings = ClockSettings(on=False)
    c.sync({"p1": "k"}, {"p2"}, 500.0)                       # off: nothing waited on, nothing spent
    c.settings = ClockSettings(on=True)
    c.sync({"p1": "k"}, {"p2"}, 600.0)
    assert c.next_event(600.0) == 620.0


def test_priority_key_follows_real_priority_changes(cards):
    s = build(cards)
    key = waiting_on(s.state)["p1"]
    with pytest.raises(ActionError):
        act(s, "p2", type="pass_priority")                 # a refused action (not their priority) changes nothing
    assert waiting_on(s.state) == {"p1": key}
    act(s, "p2", type="add_mana", player="p2", mana={"R": 1})  # another player acting does not renew it
    assert waiting_on(s.state) == {"p1": key}
    act(s, "p1", type="pass_priority")                      # passing gives a new priority (117.3d)
    after = waiting_on(s.state)
    assert after != {"p1": key}
