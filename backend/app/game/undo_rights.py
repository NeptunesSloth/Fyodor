"""-- undo policy (gap 3) -- who may undo or redo the next history entry, under the host's undo setting.

``GameSettings.undo_policy`` (set with ``configure``, host-only at a LAN table; it is table state, so saves keep it):

* ``everyone`` (the default): anyone seated may undo or redo anything, as before.
* ``own``: a player may undo (redo) only a history entry they performed, i.e. whose ``actor`` is them (the player who
  sent it). Everything the server compiled into that entry (the rules follow-ups of an intent: triggers, state-based
  actions, the draws of a pass that ran through several steps) is part of it, so it is theirs; another player's
  answer to their spell (a choice, a payment, a response) is that other player's own entry. The host gets no
  exception: their override is Snapshots & history > Restore from here (host-only), which works under every setting.
* ``host``: only the host may undo or redo. At a LAN table that is the host's own seat (a host computer watching
  without a seat is a spectator and can't undo at all, as before). At a hot-seat table everyone sits at the host
  computer, as for every host-only tool, so ``host`` allows everyone there; ``own`` still applies per acting seat.

Who performed each entry is public (the log and GET /history show every action's actor), so telling a viewer whose
action the next undo would take back reveals nothing hidden.
"""

from __future__ import annotations

from typing import Any, Literal

from app.game.actions import Action
from app.game.errors import ActionError
from app.game.history import History
from app.game.state import GameState

Op = Literal["undo", "redo"]


def entry(history: History, op: Op) -> Action | None:
    """The history entry an undo (redo) would take back (put back), if any."""
    if op == "undo":
        return history.actions[history.cursor - 1] if history.can_undo else None
    return history.actions[history.cursor] if history.can_redo else None


def refusal(state: GameState, history: History, actor: str, *, host: bool, op: Op) -> str | None:
    """Why ``actor`` may not undo (redo) now under the table's undo setting, or None (also when there is nothing to)."""
    policy = state.settings.undo_policy
    target = entry(history, op)
    if target is None or policy == "everyone":
        return None
    if policy == "host":
        return None if host else f"Only the host may {op} at this table (the host's undo setting)."
    if target.actor == actor:
        return None
    owner = state.players.get(target.actor)
    whose = f"{owner.name}'s" if owner is not None else "another player's"
    which = "the last action" if op == "undo" else "the next action to redo"
    return f"Players may only {op} their own actions at this table: {which} was {whose}."


def check(state: GameState, history: History, actor: str, *, host: bool, op: Op) -> None:
    if (why := refusal(state, history, actor, host=host, op=op)) is not None:
        raise ActionError(why)


def view_fields(state: GameState, history: History, *, host: bool) -> dict[str, Any]:
    """What a client needs to show its undo controls (the policy itself is in ``settings``): whether this viewer counts
    as the host, and, under ``own`` only, whose entry the next undo / redo would touch."""
    own = state.settings.undo_policy == "own"

    def by(op: Op) -> str | None:
        target = entry(history, op) if own else None
        return (target.actor or None) if target is not None else None

    return {"undo_host": host, "undo_by": by("undo"), "redo_by": by("redo")}
