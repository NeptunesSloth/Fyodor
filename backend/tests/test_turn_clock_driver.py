"""Turn clock (stage 3): the room's timer (app/multiplayer/turn_clock_driver.py). The hub syncs the clock on every connection, drop and
change, holds it while an action is worked out, and at zero the timer acts for the player under the room lock (or says once that it
can't). Every view carries the same clock block, spectators included, and nothing in it names a hidden choice."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import pytest

from app.game.mulligan import COMMANDER_LONDON
from app.game.session import GameSession
from app.game.turn_clock import ClockSettings, TurnClock
from app.game.visibility import SPECTATOR
from app.multiplayer import turn_clock_driver as driver
from app.multiplayer.elimination import PracticeLink
from app.multiplayer.hub import Connection, GameHub
from tests.game_helpers import act, zone
from tests.test_rules_effects import build, hand, mana, replay_matches

ACTED_ALICE = "Alice ran out of time: Fyodor acted for them."
CANT_ALICE = ("Alice ran out of time, but Fyodor can't make this choice for them. The table decides it; the host can add time or turn the "
              "clock off.")


@pytest.fixture()
def t(monkeypatch):
    """The server's clocks, by hand: ``t[0]`` is monotonic now (and wall time is a fixed offset from it)."""
    now = [1000.0]
    monkeypatch.setattr(driver, "now", lambda: now[0])
    monkeypatch.setattr(driver, "wall", lambda: 1_700_000_000.0 + now[0])
    return now


@pytest.fixture(autouse=True)
def _no_leftover_timers():
    yield
    for room_id in list(driver._drivers):
        driver.forget(room_id)


def clocked(session: GameSession, **settings: Any) -> GameSession:
    session.clock = TurnClock(settings=ClockSettings(on=True, **settings))
    return session


def seated(session: GameSession, *, mode: str = "lan"):
    hub = GameHub()
    room = hub.create_room(session, mode=mode)
    inbox: dict[str, list[dict[str, Any]]] = {"p1": [], "p2": [], SPECTATOR: []}
    conns: dict[str, Connection] = {}
    for viewer in inbox:
        async def send(message, viewer=viewer):
            inbox[viewer].append(json.loads(json.dumps(message)))

        conns[viewer] = Connection(viewer=viewer, send=send, actor=viewer if viewer != SPECTATOR else None)
        hub.connect(room, conns[viewer])
    return hub, room, inbox, conns


def block(room, pid):
    return driver.view_fields(room)["clock"]["players"][pid]


def notices(session, message):
    return sum(1 for e in session.notices if any(p.t == message for p in e.parts))


def test_only_the_waited_player_is_charged(cards, t):
    s = clocked(build(cards))
    hub, room, _, _ = seated(s)
    assert s.state.rules.priority == "p1"
    t[0] += 100
    assert block(room, "p1") == {"bank": 1430.0, "buffer": 0.0, "running": True, "away": False}  # 30 s of buffer, then 70 of bank
    assert s.clock.bank("p2", driver.now()) == 1500.0
    assert "p2" not in driver.view_fields(room)["clock"]["players"]  # (never waited on)


def test_at_zero_the_clock_passes_and_says_so(cards, t):
    s = clocked(build(cards))
    hub, room, inbox, _ = seated(s)
    s.clock.banks["p1"] = 0.0
    driver.poke(hub, room)
    before = len(s.history.actions)
    t[0] += 30
    assert asyncio.run(driver.tick(hub, room)) == ["p1"]
    assert len(s.history.actions) == before + 1
    last = s.history.actions[-1]
    assert (last.type, last.actor) == ("pass_priority", "p1")
    assert s.clock.acted_revision("p1") is not None
    for viewer, messages in inbox.items():
        assert ACTED_ALICE in json.dumps(messages[-1]["view"]["log"]), viewer
    replay_matches(s)


def test_only_show_it_does_nothing(cards, t):
    s = clocked(build(cards), at_zero="show")
    hub, room, _, _ = seated(s)
    s.clock.banks["p1"] = 0.0
    driver.poke(hub, room)
    before = len(s.history.actions)
    t[0] += 300
    assert asyncio.run(driver.tick(hub, room)) == []
    assert len(s.history.actions) == before
    assert block(room, "p1")["bank"] == 0.0
    assert not s.notices


def test_nobody_is_charged_while_an_action_resolves(cards, t, monkeypatch):
    s = clocked(build(cards))
    hub, room, _, _ = seated(s)
    t[0] += 40  # p1's buffer is spent and 10 s of bank
    prepare = GameSession.prepare

    def slow(self, *a, **k):
        t[0] += 100  # a long chain worked out off the loop
        return prepare(self, *a, **k)

    monkeypatch.setattr(GameSession, "prepare", slow)

    async def go():
        async with room.lock:
            await hub.perform(room, "p1", {"type": "pass_priority"})

    before = len(s.history.actions)
    asyncio.run(go())
    assert len(s.history.actions) == before + 1  # (the pass went through: the game moved on to p1's next priority)
    assert s.clock.bank("p1", driver.now()) == 1490.0  # charged up to the action, not while it resolved
    assert s.clock.bank("p2", driver.now()) == 1500.0


@pytest.mark.parametrize("change", ["connect", "disconnect"])
def test_a_connect_or_drop_during_an_action_charges_nobody(cards, t, monkeypatch, change):
    s = clocked(build(cards))
    hub, room, _, conns = seated(s)
    t[0] += 40  # p1's buffer is spent and 10 s of bank
    prepare = GameSession.prepare
    loop: dict[str, Any] = {}

    async def meanwhile():
        if change == "connect":
            async def send(m):
                pass

            hub.connect(room, Connection(viewer=SPECTATOR, send=send, actor=None))
        else:
            hub.disconnect(room, conns["p2"])

    def slow(self, *a, **k):
        t[0] += 50
        asyncio.run_coroutine_threadsafe(meanwhile(), loop["loop"]).result(timeout=5)  # (on the loop, without the room lock)
        t[0] += 50
        return prepare(self, *a, **k)

    monkeypatch.setattr(GameSession, "prepare", slow)

    async def go():
        loop["loop"] = asyncio.get_running_loop()
        async with room.lock:
            await hub.perform(room, "p1", {"type": "pass_priority"})

    asyncio.run(go())
    assert s.clock.bank("p1", driver.now()) == 1490.0  # held from the start of the action to its end
    assert block(room, "p1")["running"] is True  # (perform's own poke resumed the clock)


def test_a_pending_response_hold_defers_the_clock(cards, t):
    from app.multiplayer import response_call

    s = clocked(build(cards))
    hub, room, _, _ = seated(s)
    s.clock.banks["p1"] = 0.0
    driver.poke(hub, room)
    before = len(s.history.actions)
    t[0] += 30
    response_call.pending(room)["p2"] = time.monotonic()  # p2 said "Wait, I have a response!" and it hasn't landed yet
    try:
        assert asyncio.run(driver.tick(hub, room)) == []
        assert len(s.history.actions) == before and not s.notices  # nothing passed, nothing given up
        assert driver.clock_of(room).due(driver.now()) == ["p1"]  # still due
        response_call.pending(room).clear()  # (the hold landed)
        assert asyncio.run(driver.tick(hub, room)) == ["p1"]
    finally:
        response_call.forget(room.id)


def test_acted_revision_is_the_revision_that_shows_the_action(cards, t):
    s = clocked(build(cards))
    hub, room, inbox, _ = seated(s)
    asyncio.run(hub.broadcast(room))
    s.clock.banks["p1"] = 0.0
    driver.poke(hub, room)
    t[0] += 30
    assert asyncio.run(driver.tick(hub, room)) == ["p1"]
    shown = inbox["p2"][-1]
    assert ACTED_ALICE in json.dumps(shown["view"]["log"])
    assert s.clock.acted_revision("p1") == shown["revision"] == shown["view"]["game"]["revision"] == room.revision


def test_one_broadcast_one_clock_block(cards):
    s = clocked(build(cards))
    hub, room, inbox, _ = seated(s)
    asyncio.run(hub.broadcast(room))  # (the real clocks: each view built a little later than the last)
    blocks = {json.dumps(m[-1]["view"]["game"]["clock"], sort_keys=True) for m in inbox.values()}
    assert len(blocks) == 1
    assert not driver._instant


def test_a_room_replaced_under_the_same_id_gets_its_own_timer(cards, monkeypatch):
    s = clocked(build(cards))
    hub, room, _, _ = seated(s)
    s.clock.banks["p1"] = 0.0
    offset = [0.0]
    monkeypatch.setattr(driver, "now", lambda: time.monotonic() + offset[0])
    before = len(s.history.actions)

    async def run():
        driver.poke(hub, room)
        old = driver._drivers[room.id].task
        assert old is not None
        twin = hub.create_room(s, mode="lan")  # (a reload puts a new Room object under the same id)
        assert twin.id == room.id and hub.rooms[room.id] is twin
        twin.seats["p1"].connections = twin.seats["p2"].connections = 1
        offset[0] += 31
        driver.poke(hub, twin)
        assert driver._drivers[room.id].room is twin and driver._drivers[room.id].task is not old
        for _ in range(200):
            if len(s.history.actions) > before:
                return
            await asyncio.sleep(0.01)

    asyncio.run(run())
    assert len(s.history.actions) == before + 1


def test_phone_sleeps_within_grace(cards, t):  # Review Focus 1
    s = clocked(build(cards))
    hub, room, _, conns = seated(s)
    hub.disconnect(room, conns["p1"])
    assert block(room, "p1")["away"] is True
    t[0] += 90
    assert asyncio.run(driver.tick(hub, room)) == []
    hub.connect(room, Connection(viewer="p1", send=conns["p1"].send, actor="p1"))
    assert block(room, "p1") == {"bank": 1500.0, "buffer": 30.0, "running": True, "away": False}


def test_after_grace_the_absent_player_is_acted_for(cards, t):
    s = clocked(build(cards))
    hub, room, _, conns = seated(s)
    hub.disconnect(room, conns["p1"])
    bank = 1500
    t[0] += 120  # the grace ends: the timer wakes here and syncs (next_event is None after the grace until a sync)
    assert s.clock.next_event(driver.now()) is None
    assert asyncio.run(driver.tick(hub, room)) == []
    assert s.clock.next_event(driver.now()) == driver.now() + 30 + bank  # charged from now on
    t[0] += 30 + bank
    assert asyncio.run(driver.tick(hub, room)) == ["p1"]
    assert s.history.actions[-1].actor == "p1" and s.history.actions[-1].type == "pass_priority"
    replay_matches(s)


def test_simultaneous_mulligans_each_charged(cards, t):
    from tests.test_rules_first_turn_untap_s7 import table

    s = clocked(table(cards, COMMANDER_LONDON))
    hub, room, _, _ = seated(s)
    assert {p: x.status for p, x in s.state.pregame.seats.items()} == {"p1": "deciding", "p2": "deciding"}
    t[0] += 80
    driver.poke(hub, room)
    assert s.clock.banks == {"p1": 1450.0, "p2": 1450.0}
    t[0] += 1450
    assert asyncio.run(driver.tick(hub, room)) == ["p1", "p2"]
    assert s.state.pregame.finished
    assert [a.type for a in s.history.actions[-2:]] == ["mulligan_keep", "mulligan_keep"]
    replay_matches(s)


def test_never_concedes_or_eliminates(cards, t):
    s = clocked(build(cards))
    hub, room, _, _ = seated(s)
    s.clock.banks.update(p1=0.0, p2=0.0)
    driver.poke(hub, room)
    turn = s.state.turn.number

    async def run():
        for _ in range(40):
            t[0] += 30
            await driver.tick(hub, room)

    asyncio.run(run())
    r = s.state.rules
    assert s.state.turn.number > turn + 1  # across turns
    assert not r.conceded and not r.lost and r.winner is None
    assert not any(p.left for p in s.state.players.values())
    assert all(a.type != "concede" for a in s.history.actions)
    replay_matches(s)


def _manual_sol_ring(cards) -> GameSession:
    from tests.game_helpers import enable, find, make_session

    s = GameSession(enable(make_session(cards).state), cards=cards)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="draw", count=7)
    ring = find(s.state, "Sol Ring", "p1")
    act(s, "p1", type="set_card_automation", card_id=ring.id, mode="manual")
    act(s, "p1", type="play_land", card_id=find(s.state, "Mountain", "p1").id)
    act(s, "p1", type="cast_spell", card_id=ring.id)
    assert s.state.rules.decision.kind == "manual_resolution"
    return s


def test_refused_everything_says_so_once(cards, t):  # Review Focus 5
    s = clocked(_manual_sol_ring(cards))
    hub, room, inbox, _ = seated(s)
    s.clock.banks["p1"] = 0.0
    driver.poke(hub, room)
    before, decision = len(s.history.actions), s.state.rules.decision.id
    t[0] += 30

    async def three():
        return [await driver.tick(hub, room) for _ in range(3)]

    assert asyncio.run(three()) == [[], [], []]
    assert notices(s, CANT_ALICE) == 1
    assert CANT_ALICE in json.dumps(inbox[SPECTATOR][-1]["view"]["log"])  # (the table hears it)
    assert len(s.history.actions) == before and s.state.rules.decision.id == decision  # nothing applied
    assert s.clock.next_event(driver.now()) is None  # no wake-up at a past time
    t[0] += 600
    assert s.clock.next_event(driver.now()) is None and asyncio.run(driver.tick(hub, room)) == []
    assert notices(s, CANT_ALICE) == 1
    replay_matches(s)


def test_an_engine_failure_ends_only_the_task(cards, monkeypatch, caplog):
    s = clocked(build(cards))
    hub, room, _, _ = seated(s)
    s.clock.banks["p1"] = 0.0
    offset = [0.0]
    monkeypatch.setattr(driver, "now", lambda: time.monotonic() + offset[0])
    before = len(s.history.actions)
    tasks: list[Any] = []

    async def failing(*a, **k):
        raise RuntimeError("engine exploded")

    async def run():
        driver.poke(hub, room)
        hub.perform = failing  # type: ignore[method-assign]
        offset[0] += 31  # past p1's deadline
        driver.poke(hub, room)
        first = driver._drivers[room.id].task
        tasks.append(first)
        for _ in range(200):
            if first.done():
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0)  # (the done-callback)
        assert first.done() and isinstance(first.exception(), RuntimeError)
        assert not room.lock.locked()
        del hub.perform  # the engine works again
        driver.poke(hub, room)
        second = driver._drivers[room.id].task
        tasks.append(second)
        assert second is not None and second is not first
        for _ in range(200):
            if len(s.history.actions) > before:
                break
            await asyncio.sleep(0.01)

    with caplog.at_level(logging.ERROR, logger=driver.__name__):
        asyncio.run(run())
    assert any(r.levelno == logging.ERROR and r.exc_info and "engine exploded" in str(r.exc_info[1]) for r in caplog.records)
    assert len(s.history.actions) == before + 1 and s.history.actions[-1].actor == "p1"  # the re-armed timer acted
    replay_matches(s)


def test_every_viewer_sees_the_same_clock(cards, t):
    s = clocked(build(cards))
    hub, room, _, _ = seated(s)
    act(s, "p1", type="draw", count=10)
    t[0] += 12

    def blocks():
        return {v: hub.view(room, v)["game"]["clock"] for v in ("p1", "p2", SPECTATOR)}

    def shape(x):
        return {k: shape(v) for k, v in x.items()} if isinstance(x, dict) else type(x).__name__

    driver.poke(hub, room)
    at_priority = blocks()
    opt = hand(s, "p1", "Opt")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=opt.id)
    d = s.state.rules.decision
    assert d.kind == "choose_cards" and d.player == "p1"  # a private look at the library top
    hub.after_change(room)
    t[0] += 7
    searching = blocks()
    assert searching["p2"] == searching[SPECTATOR] == searching["p1"]
    assert at_priority["p2"] == at_priority[SPECTATOR] == at_priority["p1"]
    assert shape(searching["p2"]) == shape(at_priority["p2"])  # the same keys whatever p1 is deciding
    raw = json.dumps(searching)
    assert d.id not in raw and zone(s.state, "p1", "library")[0] not in raw
    assert searching["p2"]["players"]["p1"]["running"] is True


def test_a_broadcast_carries_the_current_wait(cards, t):
    s = clocked(build(cards))
    hub, room, inbox, _ = seated(s)
    t[0] += 40  # p1's buffer is spent
    act(s, "p1", type="pass_priority")  # (a change the hub hasn't been told of: the broadcast syncs)
    asyncio.run(hub.broadcast(room))
    sent = inbox[SPECTATOR][-1]["view"]["game"]["clock"]
    assert sent["players"]["p1"] == {"bank": 1490.0, "buffer": 30.0, "running": True, "away": False}  # a new wait, a new buffer
    assert sent["sent_at"] == 1_700_000_000.0 + t[0]


def test_the_task_fires_without_anyone_acting(cards, monkeypatch):
    s = clocked(build(cards))
    hub, room, _, _ = seated(s)
    s.clock.banks["p1"] = 0.0
    offset = [0.0]
    monkeypatch.setattr(driver, "now", lambda: time.monotonic() + offset[0])
    before = len(s.history.actions)

    async def run():
        driver.poke(hub, room)
        offset[0] += 31
        driver.poke(hub, room)
        for _ in range(200):
            if len(s.history.actions) > before:
                return
            await asyncio.sleep(0.01)

    asyncio.run(run())
    assert len(s.history.actions) == before + 1 and s.history.actions[-1].type == "pass_priority"
    assert notices(s, ACTED_ALICE) == 1


def test_the_task_wakes_at_the_grace_end_and_syncs(cards, monkeypatch):
    """After the grace the model charges only from the next sync: the timer syncs when it wakes there (and does not spin)."""
    s = clocked(build(cards), buffer_seconds=5, grace_seconds=30)
    hub, room, _, conns = seated(s)
    s.clock.banks["p1"] = 0.0
    offset = [0.0]
    monkeypatch.setattr(driver, "now", lambda: time.monotonic() + offset[0])
    ticks = [0]
    tick = driver.tick

    async def counted(*a):
        ticks[0] += 1
        return await tick(*a)

    monkeypatch.setattr(driver, "tick", counted)

    async def run():
        hub.disconnect(room, conns["p1"])
        offset[0] += 29.9  # the grace ends in 0.1 s
        driver.poke(hub, room)
        for _ in range(200):
            if s.clock.public(driver.now(), 0)["players"]["p1"]["running"]:
                break
            await asyncio.sleep(0.01)
        assert s.clock.public(driver.now(), 0)["players"]["p1"]["running"]  # the timer woke at the grace end and synced
        await asyncio.sleep(0.2)
        assert ticks[0] <= 2  # (asleep until the buffer runs out: no spin)
        offset[0] += 5
        driver.poke(hub, room)
        for _ in range(200):
            if len(s.history.actions) > before:
                return
            await asyncio.sleep(0.01)

    before = len(s.history.actions)
    asyncio.run(run())
    assert len(s.history.actions) == before + 1 and s.history.actions[-1].type == "pass_priority"


def test_not_offered_on_hot_seat_or_practice_or_sandbox(cards, t):
    hot = clocked(build(cards))
    hub, room, _, _ = seated(hot, mode="local")
    hot.clock.banks["p1"] = 0.0
    t[0] += 1000
    assert driver.view_fields(room) == {} and asyncio.run(driver.tick(hub, room)) == []
    assert "clock" not in hub.view(room, "p1")["game"]

    practice = clocked(build(cards))
    hub = GameHub()
    room = hub.create_practice(practice, PracticeLink(live="x", seat="p1", game=1))
    practice.clock.banks["p1"] = 0.0
    t[0] += 1000
    assert driver.view_fields(room) == {} and asyncio.run(driver.tick(hub, room)) == []

    sandbox = clocked(build(cards))
    sandbox.state.format = "sandbox"
    hub, room, _, _ = seated(sandbox)
    sandbox.clock.banks["p1"] = 0.0
    t[0] += 1000
    assert driver.view_fields(room) == {} and asyncio.run(driver.tick(hub, room)) == []
    for s in (hot, practice, sandbox):
        assert not s.notices

    # (offered, but nobody has set a clock: the settings, so the host can turn one on)
    plain = build(cards)
    hub, room, _, _ = seated(plain)
    assert driver.view_fields(room) == {"clock": {"settings": ClockSettings().model_dump()}}
    assert asyncio.run(driver.tick(hub, room)) == []
