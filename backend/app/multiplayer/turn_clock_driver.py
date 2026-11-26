"""-- turn clock (stage 3) -- the room's timer: the server-owned turn clock (app/game/turn_clock.py) kept in step with the table, and acted on
at zero.

The hub calls :func:`poke` after every change, broadcast, connection and drop (and :func:`hold` as an action begins: nobody is charged
while it is worked out). ``poke`` syncs the clock with who the engine waits on and who is connected, and (re)arms the room's one timer
task, which sleeps until the clock's next event (a deadline, the end of a grace) or a wake-up, then runs :func:`tick` under the room lock:
for each player whose clock reached zero (when the host chose "Act for the player") it tries the safest default
(app/game/clock_defaults.py) as an ordinary action of theirs; when the engine takes none of them, it says so once and leaves the choice to
the table. It never concedes or eliminates anyone.

The clock's only failure path: :func:`tick` catches only an action the engine refuses (``ActionError``, which ``AutomationError`` is, and
``ValidationError``). Anything else ends the task (the done-callback logs it at error level) and leaves the table as it was; the next
``poke`` (every broadcast) starts a fresh task.

Offered at LAN tables of a Commander game only (never hot-seat, practice or sandbox tables).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from app.game import clock_defaults
from app.game.errors import ActionError
from app.game.turn_clock import ClockSettings, TurnClock, waiting_on

if TYPE_CHECKING:
    from app.multiplayer.hub import GameHub, Room

log = logging.getLogger(__name__)

now: Callable[[], float] = time.monotonic  # what the clock charges by (tests patch it)
wall: Callable[[], float] = time.time  # when a view was built, for the browser's own countdown

# Neither names the choice: the action's own log entry already follows the visibility rules
ACTED = "{name} ran out of time: Fyodor acted for them."
CANT = ("{name} ran out of time, but Fyodor can't make this choice for them. The table decides it; the host can add time or turn the "
        "clock off.")


@dataclass
class Driver:
    task: asyncio.Task[None] | None = None
    wake: asyncio.Event | None = None  # cuts the sleep short (a change: the next event may have moved)


_drivers: dict[str, Driver] = {}


def offered(room: Room) -> bool:
    return room.mode == "lan" and room.practice is None and room.game is not None and room.game.state.format == "commander"


def clock_of(room: Room) -> TurnClock | None:
    return room.game.clock if room.game is not None and offered(room) else None


def _sync(room: Room, clock: TurnClock) -> None:
    connected = {pid for pid, s in room.seats.items() if s.connections > 0 and not s.bot}
    # -- final board -- a finished table is looked at, not played: nobody is waited on
    waiting = {} if room.night.final_board() is not None else waiting_on(room.session.state)
    clock.sync(waiting, connected, now())


def poke(hub: GameHub, room: Room) -> None:
    """Sync the clock with the table, and (in the event loop) wake or start the room's one timer task."""
    clock = clock_of(room)
    if clock is None or hub.rooms.get(room.id) is not room:
        return
    _sync(room, clock)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # (off the loop: synced; the next poke inside it arms the timer)
    d = _drivers.setdefault(room.id, Driver())
    if d.task is not None and not d.task.done():
        if d.wake is not None:
            d.wake.set()
        return
    if clock.next_event(now()) is None:
        return
    d.wake = asyncio.Event()
    d.task = loop.create_task(_run(hub, room, d))
    d.task.add_done_callback(_ended)


def hold(room: Room) -> None:
    """An action begins: nobody is charged until the next sync (the hub's poke after it)."""
    clock = clock_of(room)
    if clock is not None:
        clock.hold(now())


async def tick(hub: GameHub, room: Room) -> list[str]:
    """Act for each player whose clock reached zero (under the room lock); returns the players it acted for."""
    acted: list[str] = []
    changed = False
    async with room.lock:
        if hub.rooms.get(room.id) is not room or room.game is None:
            return []
        clock = clock_of(room)
        if clock is None:
            return []
        session = room.game
        _sync(room, clock)
        for _ in range(len(session.state.seat_order) * 2):
            due = clock.due(now())
            if not due:
                break
            pid = due[0]
            key = waiting_on(session.state).get(pid)
            for payload in clock_defaults.answers(session.state, pid, session.cards):
                try:
                    await hub.perform(room, pid, payload)
                except (ActionError, ValidationError):
                    continue
                clock.mark_acted(pid, room.revision)
                session.notice(ACTED.format(name=room.seat_name(pid)))
                hub.after_change(room)
                _sync(room, clock)
                acted.append(pid)
                changed = True
                if key is not None and waiting_on(session.state).get(pid) == key:
                    clock.give_up(pid)  # (accepted, yet the very same wait: never answered twice in a row)
                break
            else:
                clock.give_up(pid)  # (said once for this wait: ``due`` leaves it out until the wait changes)
                session.notice(CANT.format(name=room.seat_name(pid)))
                changed = True
    if changed:
        await hub.broadcast(room)
    return acted


async def _run(hub: GameHub, room: Room, d: Driver) -> None:
    try:
        while True:
            if d.wake is None:
                return
            d.wake.clear()  # (before the clock is read: a poke from here on wakes the sleep below)
            clock = clock_of(room)
            if hub.rooms.get(room.id) is not room or clock is None:
                return
            at = clock.next_event(now())
            if at is None:
                return
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(d.wake.wait(), max(0.0, at - now()))
            await tick(hub, room)  # (syncs first: a grace that ended starts charging here)
    finally:
        if d.task is asyncio.current_task():
            d.task = None


def _ended(task: asyncio.Task[None]) -> None:
    if not task.cancelled() and (exc := task.exception()) is not None:
        log.error("The turn clock's timer failed; the table goes on and the next change restarts it", exc_info=exc)


def view_fields(room: Room) -> dict[str, Any]:
    """The clock block of every view (the same for every viewer, spectators included)."""
    if not offered(room):
        return {}
    clock = room.session.clock
    if clock is None:
        return {"clock": {"settings": ClockSettings.model_validate({}).model_dump()}}
    return {"clock": clock.public(now(), wall())}


def forget(room_id: str) -> None:
    d = _drivers.pop(room_id, None)
    if d is not None and d.task is not None and not d.task.done():
        d.task.cancel()
