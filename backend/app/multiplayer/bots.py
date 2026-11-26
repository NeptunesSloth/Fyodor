"""-- test opponent -- pacing: the server plays a test opponent's actions (app/game/bot.py) one at a time, in the event loop, with a short
pause between them so the player can follow them on the table and in the log.

After any change to a table (``GameHub.after_change``, a broadcast, a client connecting) :func:`poke` starts the room's driver task unless
one is running. The driver waits the pause, then, under the room's lock (like any action), plays one action for the opponent the game waits
for and broadcasts the table; again until no opponent is waited for. It never blocks the loop (the pause is ``asyncio.sleep``; one action is
one short engine call, as a player's own), and never runs two at once for one room.

The table's **bot speed** (the top bar's toggle; in memory, not part of the game, so never in its history):

* ``normal``: a pause of ``DELAYS["normal"]`` between actions; ``fast``: a very short one;
* ``step``: nothing is played until the player asks for one action (``POST /games/{id}/bot/step``).

``MAX_RUN`` caps how many actions the opponents play without the player acting in between (a policy that loops stops there, with a notice;
any action of the player's starts a new run).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from app.game import bot
from app.game.autoseat import bots_of
from app.multiplayer import response_call

if TYPE_CHECKING:
    from app.multiplayer.hub import GameHub, Room

log = logging.getLogger(__name__)

Speed = Literal["normal", "fast", "step"]
SPEEDS: tuple[Speed, ...] = ("normal", "fast", "step")
DELAYS: dict[str, float] = {"normal": 0.7, "fast": 0.12, "step": 0.0}
MAX_RUN = 400  # actions in a row without the player acting


@dataclass
class Driver:
    speed: Speed = "normal"
    steps: int = 0  # Step mode: actions the player asked for and not played yet
    task: asyncio.Task[None] | None = None
    run: int = 0  # actions played since the player last acted
    seen: int = -1  # the history position after the last action this driver played
    stuck: bool = False  # said once: the opponent couldn't act
    wake: asyncio.Event | None = None  # cuts a pause short (a new speed, Step's button)


_drivers: dict[str, Driver] = {}


def driver(room: Room) -> Driver:
    d = _drivers.get(room.id)
    if d is None:
        d = _drivers[room.id] = Driver()
    return d


def has_bot(room: Room) -> bool:
    return room.game is not None and bool(bots_of(room.game.state))


def waiting(room: Room) -> bool:
    """An opponent the game waits for (cheap: no view is built)."""
    return room.game is not None and bot.pending(room.game.state) is not None


def view_fields(room: Room) -> dict[str, Any]:
    """The top bar's bot toggle: its speed, and whether an opponent's action is waiting (Step plays it)."""
    if not has_bot(room):
        return {}
    d = driver(room)
    return {"bot": {"speed": d.speed, "waiting": waiting(room), "stuck": d.stuck}}


def poke(hub: GameHub, room: Room) -> None:
    """Start the room's driver if an opponent may have something to do and none is running (a no-op outside the event loop: the next
    change, broadcast or connection inside it starts it)."""
    if not has_bot(room):
        return
    d = driver(room)
    if d.task is not None and not d.task.done():
        return
    if d.speed == "step" and d.steps <= 0:
        return
    if not waiting(room):
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    d.task = loop.create_task(_drive(hub, room, d))


async def _drive(hub: GameHub, room: Room, d: Driver) -> None:
    try:
        while True:
            pause = DELAYS.get(d.speed, 0.0)
            d.wake = asyncio.Event()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(d.wake.wait(), pause)
            async with room.lock:
                if hub.rooms.get(room.id) is not room or room.game is None:
                    return
                if room.night.final_board() is not None:
                    return  # -- final board -- a finished table is looked at, not played
                if d.speed == "step" and d.steps <= 0:
                    return
                if response_call.waiting(room):
                    continue  # -- I have a response -- a player called for a hold that hasn't landed yet: the opponent waits for it
                session = room.game
                history = session.history
                if history.cursor != d.seen:  # the player (or an undo) changed the table since: a new run
                    d.run = 0
                if d.run >= MAX_RUN:
                    if not d.stuck:
                        d.stuck = True
                        session.notice(f"The test opponent played {MAX_RUN} actions in a row and stopped. Act yourself, or pause "
                                       "automation, to go on.")
                        hub.persist(room)
                    return
                played = bot.step(session)
                if played is None:
                    if waiting(room) and not d.stuck:
                        d.stuck = True
                        session.notice("The test opponent can't decide this by itself. Pause automation to go on by hand.")
                    return
                d.stuck = False
                d.run += 1
                d.seen = history.cursor
                if d.speed == "step":
                    d.steps -= 1
                hub.after_change(room)
            await hub.broadcast(room)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - the driver must never take the server down: the table goes on by hand
        log.exception("The test opponent's driver failed")
    finally:
        if d.task is asyncio.current_task():
            d.task = None


def set_speed(hub: GameHub, room: Room, speed: Speed) -> None:
    d = driver(room)
    d.speed = speed
    d.steps = 0
    d.stuck = False
    _wake(d)
    poke(hub, room)


def step_once(hub: GameHub, room: Room) -> None:
    """Step mode: play the opponent's next action (at any speed: one more right away)."""
    d = driver(room)
    d.steps = 1
    d.stuck = False
    _wake(d)
    poke(hub, room)


def _wake(d: Driver) -> None:
    if d.wake is not None:
        d.wake.set()


def forget(room_id: str) -> None:
    d = _drivers.pop(room_id, None)
    if d is not None and d.task is not None and not d.task.done():
        d.task.cancel()
