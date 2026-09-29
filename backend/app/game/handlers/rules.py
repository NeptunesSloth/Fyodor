"""Applying rules-engine output. Pure replay: nothing here runs rules code.

A rules intent (``play_land``, ``pass_priority``, …) was compiled by ``app.rules.engine`` into
ordinary table actions, recorded on the intent as ``r``. Applying the intent replays exactly those
steps, so undo/redo, saves and history replay never depend on the current rules code.
"""

from __future__ import annotations

from app.game import actions as A
from app.game import ops
from app.game.errors import ActionError
from app.game.ops import log, text
from app.game.rules_state import RulesState, track
from app.game.state import GameState

_NOT_A_STEP = A.INTENT_TYPES | {"run_macro", "restore_state", "response_open"}


def apply_intent(state: GameState, a: A.Action) -> None:
    from app.game.engine import HANDLERS  # the engine imports this module

    steps = getattr(a, "r", None)
    if not steps:
        raise ActionError("unresolved rules intent")
    for payload in steps:
        step = A.parse_action(payload)
        if step.type in _NOT_A_STEP:
            raise ActionError("Invalid rules step")
        HANDLERS[step.type](state, step)
        track(state)


def rules_sync(state: GameState, a: A.RulesSync) -> None:
    state.rules = RulesState.model_validate(a.rules) if a.rules is not None else None


def rules_log(state: GameState, a: A.RulesLog) -> None:
    parts = [text(a.text)]
    for cid in a.card_ids:
        if cid in state.cards:
            parts += [text(" "), ops.card_part(state, state.cards[cid])]
    log(state, a.actor, a.ts, parts, kind=a.kind)
