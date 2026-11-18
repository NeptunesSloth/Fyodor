"""-- I have a response -- and -- flip the table -- : the room's side of two things a player says out loud.

"Wait, I have a response!" (``set_prefs respond=True``, app/rules/response_call.py) is heard the moment it arrives, before it waits
for the table's lock behind whatever is being worked out (``early``, from the action routes): every connection gets a short shout
at once, the hold goes into the room's pending holds, which the engine takes in at the next priority of an action being worked out
right now (a long chain: ``InterimStream.calls``), and the test opponent's driver waits while one is pending (app/multiplayer/bots.py)
so it never races past it. The recorded action then lands as usual (``after`` clears the pending hold).

A concession with ``flip`` (Concede and flip the table) sends every connection a cosmetic flip once it is applied (``after``): only
ever for the player who conceded. The fun flip without conceding is a soft signal (app/api/night.py, kind "flip"). In memory only:
nothing here is saved, recorded or replayed.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from app.rules.plan import live_players

if TYPE_CHECKING:
    from app.multiplayer.hub import GameHub, Room

PENDING_FOR = 8.0  # seconds a pending hold keeps the test opponent waiting, at most (its action normally lands well before)
SHOUT_EVERY = 1.5  # seconds between two shouts from one player (pressing again cancels: no shout)
FLIP_EVERY = 30.0  # seconds between two table flips from one player

_pending: dict[str, dict[str, float]] = {}
_last: dict[str, float] = {}
_tasks: set[asyncio.Task[None]] = set()


def pending(room: Room) -> dict[str, float]:
    """The room's pending holds: player -> when heard (the same dict every time: the engine reads it from its worker thread)."""
    return _pending.setdefault(room.id, {})


def waiting(room: Room) -> bool:
    """A hold heard and not applied yet (the test opponent waits for it)."""
    calls = _pending.get(room.id)
    if not calls:
        return False
    now = time.monotonic()
    for pid, at in list(calls.items()):
        if now - at > PENDING_FOR:
            calls.pop(pid, None)
    return bool(calls)


def _respond(action: Any) -> bool | None:
    if not isinstance(action, dict) or action.get("type") != "set_prefs":
        return None
    value = action.get("respond")
    return value if isinstance(value, bool) else None


def early(hub: GameHub, room: Room, actor: str | None, action: Any) -> None:
    """Before the action waits for the table's lock: a hold is heard now (the shout, the pending hold)."""
    on = _respond(action)
    if on is None or actor is None or room.game is None:
        return
    state = room.game.state
    r = state.rules
    if r is None or state.settings.automation == "off" or r.paused or actor not in live_players(state):
        return  # (the action itself says why not)
    calls = pending(room)
    if not on:
        calls.pop(actor, None)
        return
    if r.priority == actor and r.decision is None and room.acting is None:
        return  # they hold priority already
    calls[actor] = time.monotonic()
    key = f"{room.id}:shout:{actor}"
    now = time.monotonic()
    if now - _last.get(key, -1e9) < SHOUT_EVERY:
        return
    _last[key] = now
    _later(_to_everyone(hub, room, {"type": "signal", "kind": "response", "from": actor, "from_name": room.seat_name(actor), "on": True}))


def after(hub: GameHub, room: Room, actor: str, payload: Any, *, applied: bool) -> None:
    """After an action was worked out (applied or refused): a pending hold of that player is done; a concession with a flip shows it."""
    if _respond(payload) is not None:
        calls = _pending.get(room.id)
        if calls is not None:
            calls.pop(actor, None)
        if applied:
            from app.multiplayer import bots

            bots.poke(hub, room)
    if applied and isinstance(payload, dict) and payload.get("type") == "concede" and payload.get("flip"):
        flip(hub, room, actor, concede=True)


def flip_wait(room: Room, actor: str) -> float:
    """Seconds until ``actor`` may flip the table again (0: now)."""
    return max(0.0, FLIP_EVERY - (time.monotonic() - _last.get(f"{room.id}:flip:{actor}", -1e9)))


def flip(hub: GameHub, room: Room, actor: str, *, concede: bool) -> None:
    """(╯°□°)╯︵ ┻━┻ on every table: cosmetic, for ``actor``'s own side only."""
    _last[f"{room.id}:flip:{actor}"] = time.monotonic()
    _later(_to_everyone(hub, room, {"type": "signal", "kind": "flip", "from": actor, "from_name": room.seat_name(actor),
                                    "concede": concede}))


def forget(room_id: str) -> None:
    _pending.pop(room_id, None)
    for key in [k for k in _last if k.startswith(f"{room_id}:")]:
        del _last[key]


async def _to_everyone(hub: GameHub, room: Room, message: dict[str, Any]) -> None:
    for conn in list(room.connections.values()):
        try:
            await conn.send(message)
        except Exception:  # noqa: BLE001 - best effort, like every push
            hub.disconnect(room, conn)


def _later(coro: Any) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        coro.close()
        return
    task = loop.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
