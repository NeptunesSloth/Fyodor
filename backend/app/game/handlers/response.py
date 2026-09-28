"""The Response helper: "anything in response?" without ever locking the table.

SIMPLE mode: putting something on the stack asks everyone else to RESPOND or PASS. Resolving
the top of the stack and moving to the next step/turn ask first too, and happen automatically
once everyone has passed. The opener can proceed anyway (``force``), the host can force a
window shut, and players can AUTO-PASS for the rest of the turn. Nothing is enforced.
"""

from __future__ import annotations

from typing import Any, Literal

from app.game import actions as A
from app.game.errors import ActionError
from app.game.ops import log, pname, text
from app.game.state import PHASES, STACK, GameState, ResponseWindow

PHASE_NAMES = {"main1": "main phase 1", "main2": "main phase 2", "begin_combat": "combat", "declare_attackers": "attackers",
               "declare_blockers": "blockers", "combat_damage": "combat damage", "end_combat": "end of combat",
               "end": "the end step"}


def enabled(state: GameState) -> bool:
    return state.settings.priority_helper == "simple" and (state.pregame is None or state.pregame.finished)


def _others(state: GameState, actor: str) -> list[str]:
    turn = state.turn.number
    return [p for p in state.seat_order if p != actor and state.auto_pass.get(p) != turn]


def _just_passed(state: GameState) -> bool:
    """Everyone passed on the last window and nothing has happened since."""
    return state.passed_at == state.seq


def wrap(state: GameState, a: Any) -> Any:
    """Turn a resolve / step / turn request into a response check when the helper is on."""
    if not isinstance(a, A.Phase | A.NextTurn | A.ResolveTop) or a.force or not enabled(state):
        return a
    if isinstance(a, A.Phase) and a.to == "prev":
        return a
    if not _others(state, a.actor) or _just_passed(state):
        return a
    kind: Literal["resolve", "phase", "turn"]
    if isinstance(a, A.ResolveTop):
        stack = state.zones.get(STACK, [])
        if not stack:
            return a
        top = state.cards[stack[-1]]
        kind, what = "resolve", f"resolve {top.name if not top.face_down else 'a face-down spell'}"
    elif isinstance(a, A.NextTurn):
        kind, what = "turn", "end the turn"
    else:
        target = a.to
        if target == "next":
            i = PHASES.index(state.turn.phase)
            target = PHASES[(i + 1) % len(PHASES)]
        kind, what = "phase", f"move to {PHASE_NAMES.get(target, target)}"
    return A.ResponseOpen(actor=a.actor, ts=a.ts, kind=kind, text=what, intent=a.model_dump(mode="json"))


def _open(state: GameState, actor: str, kind: str, what: str, intent: dict[str, Any] | None) -> None:
    waiting = _others(state, actor)
    state.response = ResponseWindow(id=f"r{state.seq}", kind=kind, opener=actor, text=what,  # type: ignore[arg-type]
                                    waiting=waiting, intent=intent)


def open_window(state: GameState, a: A.ResponseOpen) -> None:
    _open(state, a.actor, a.kind, a.text, a.intent)
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" wants to {a.text} — any responses?")], kind="minor")
    if not state.response or not state.response.waiting:
        _complete(state, a.actor, a.ts)


def on_stack_add(state: GameState, actor: str, what: str) -> None:
    """Called when something goes on the stack: ask the others."""
    if not enabled(state) or not _others(state, actor):
        return
    _open(state, actor, "stack", what, None)


def _complete(state: GameState, actor: str, ts: float) -> None:
    """Everyone passed: close the window and carry out what was asked for."""
    window = state.response
    state.response = None
    if window is None:
        return
    if window.intent is not None:
        _apply_intent(state, window.intent)  # the passes were for this; the next request asks again
    else:
        state.passed_at = state.seq  # everyone passed on the stack: resolving right now needn't ask again
        log(state, actor, ts, [text("Everyone passed.")], kind="minor")


def _apply_intent(state: GameState, intent: dict[str, Any]) -> None:
    from app.game.engine import HANDLERS  # the engine imports this module

    action = A.parse_action(intent)
    HANDLERS[action.type](state, action)


def pass_(state: GameState, a: A.ResponsePass) -> None:
    w = state.response
    if w is None or a.actor not in w.waiting:
        raise ActionError("Nothing to pass on")
    w.waiting.remove(a.actor)
    w.passed.append(a.actor)
    if not w.waiting and w.responder is None:
        _complete(state, a.actor, a.ts)


def respond(state: GameState, a: A.ResponseRespond) -> None:
    w = state.response
    if w is None or a.actor == w.opener:
        raise ActionError("Nothing to respond to")
    w.responder = a.actor
    w.waiting = [p for p in w.waiting if p != a.actor]
    held = f" — {state.players[w.opener].name}'s request to {w.text} is on hold" if w.intent else ""
    w.intent = None
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" responds{held}.")])


def auto(state: GameState, a: A.ResponseAutoPass) -> None:
    if a.on:
        state.auto_pass[a.actor] = state.turn.number
        w = state.response
        if w is not None and a.actor in w.waiting:
            pass_(state, A.ResponsePass(actor=a.actor, ts=a.ts))
    else:
        state.auto_pass.pop(a.actor, None)


def close(state: GameState, a: A.ResponseClose) -> None:
    w = state.response
    if w is None:
        raise ActionError("No response check is open")
    if not a.as_host and a.actor not in (w.opener, w.responder):
        raise ActionError("Only the player who asked (or the host) can close this")
    if a.apply_intent and w.intent is not None:
        state.response = None
        who = "The host" if a.as_host else state.players[a.actor].name
        log(state, a.actor, a.ts, [text(f"{who} went ahead: {w.text}.")], kind="minor")
        _apply_intent(state, w.intent)
    else:
        state.response = None
        log(state, a.actor, a.ts, [pname(state, a.actor), text(" closed the response check.")], kind="minor")


def clear(state: GameState) -> None:
    """Steps and turns end any open check."""
    state.response = None
