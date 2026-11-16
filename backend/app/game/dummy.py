"""-- target dummy -- the server answers for the table's target dummy (app/game/handlers/dummy.py) so it never holds the game up.

After each action a player sends, ``GameSession`` asks :func:`to_answer` what the dummy has to do now and performs it as the dummy,
again and again (at most ``MAX_ANSWERS`` times), until nothing is waiting for it:

* opening hands: it keeps (it holds no cards);
* rules automation running: it passes priority, declares no attackers and no blockers, and answers any other choice with the
  smallest answer it allows (none when it may choose nothing, else the first options), trying a few if the engine refuses one.

Each answer is an ordinary recorded action whose actor is the dummy, so history replays it like any other (deterministic under
undo, redo and a reload). Undo and redo treat the dummy's answers as part of the action they answered: one undo takes the
player's action back with them (``GameSession.undo``). Nothing is answered while automation is off or paused (no priority to
pass; the dummy's turns are skipped anyway), or once the game is over.
"""

from __future__ import annotations

from typing import Any

from app.game.control import decider_of
from app.game.handlers.dummy import dummy_of
from app.game.rules_state import Decision
from app.game.state import GameState

MAX_ANSWERS = 64  # answers in a row after one action (a full combat with triggers needs a handful)
MAX_TRIES = 4  # answers tried for one decision before giving up on it


def is_dummy(state: GameState, pid: str | None) -> bool:
    p = state.players.get(pid) if pid else None
    return p is not None and p.dummy


def to_answer(state: GameState) -> tuple[str, list[dict[str, Any]]] | None:
    """The dummy and the answers to try in turn (the first the server accepts is the one), or None when it has nothing to do."""
    pid = dummy_of(state)
    if pid is None or state.players[pid].left:
        return None
    pregame = state.pregame
    if pregame is not None and not pregame.finished:
        seat = pregame.seats.get(pid)
        return (pid, [{"type": "mulligan_keep"}]) if seat is not None and seat.status == "deciding" else None
    r = state.rules
    if r is None or state.settings.automation == "off" or r.paused or r.winner is not None or r.draw_reason is not None:
        return None
    if pid in r.lost or pid in r.conceded:
        return None
    d = r.decision
    if d is not None:
        return (pid, answers(d)) if decider_of(state, d) == pid else None
    if r.priority == pid:
        return pid, [{"type": "pass_priority"}]
    return None


def answers(d: Decision) -> list[dict[str, Any]]:
    """The dummy's answers to decision ``d``, most passive first: no attackers / blockers; else nothing when it may choose nothing,
    then the first options it must choose, then each other option alone."""
    if d.kind == "declare_attackers":
        return [{"type": "declare_attackers"}]
    if d.kind == "declare_blockers":
        return [{"type": "declare_blockers"}]
    ids = [o.id for o in d.options]

    def choose(picked: list[str]) -> dict[str, Any]:
        return {"type": "choose", "decision_id": d.id, "option_ids": picked}

    out: list[dict[str, Any]] = []
    if d.kind == "order":  # (its triggers, in the order offered)
        out.append(choose(ids))
    if d.min_choices <= 0:
        out.append(choose([]))
    need = max(1, d.min_choices)
    if len(ids) >= need:
        out.append(choose(ids[:need]))
    if need == 1:
        out += [choose([i]) for i in ids[1:]]
    return out[:MAX_TRIES]
