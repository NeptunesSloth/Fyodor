"""Applying rules-engine output. Pure replay: nothing here runs rules code.

A rules intent (``play_land``, ``pass_priority``, …) was compiled by ``app.rules.engine`` into
ordinary table actions, recorded on the intent as ``r``. Applying the intent replays exactly those
steps, so undo/redo, saves and history replay never depend on the current rules code.
"""

from __future__ import annotations

from app.game import actions as A
from app.game import ops
from app.game.errors import ActionError
from app.game.handlers.players import change_life
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


def rules_mana(state: GameState, a: A.RulesMana) -> None:
    if a.empty_all:
        for p in state.players.values():
            p.mana = {}
        return
    player = state.players.get(a.player)
    if player is None:
        raise ActionError("Unknown player")
    tapped = []
    for cid in a.tap:
        card = ops.card(state, cid)
        if card.tapped:
            raise ActionError(f"{card.name or 'That card'} is already tapped")
        card.tapped = True
        tapped.append(card)
    pool = player.mana
    for color, amount in a.delta.items():
        value = pool.get(color, 0) + amount
        if value < 0:
            raise ActionError("Not enough mana in the pool")
        if value:
            pool[color] = value
        else:
            pool.pop(color, None)
    if a.life:
        change_life(state, a.player, player.life - a.life)
    if a.label:
        parts = [ops.pname(state, a.player), text(" " + a.label)]
        if tapped:
            parts += [text(" (tapped "), ops.group(state, tapped), text(")")]
        log(state, a.actor, a.ts, parts, kind="mana")
    for cid in a.sacrifice:
        card = ops.card(state, cid)
        if card.is_token:
            ops.delete(state, card)
        else:
            ops.move_card(state, card, f"{card.owner}:graveyard")


def rules_log(state: GameState, a: A.RulesLog) -> None:
    parts = [text(a.text)]
    for cid in a.card_ids:
        if cid in state.cards:
            parts += [text(" "), ops.card_part(state, state.cards[cid])]
    log(state, a.actor, a.ts, parts, kind=a.kind)
