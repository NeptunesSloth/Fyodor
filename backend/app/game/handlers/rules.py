"""Applying rules-engine output. Pure replay: nothing here runs rules code.

A rules intent (``play_land``, ``pass_priority``, …) was compiled by ``app.rules.engine`` into
ordinary table actions, recorded on the intent as ``r``. Applying the intent replays exactly those
steps, so undo/redo, saves and history replay never depend on the current rules code.
"""

from __future__ import annotations

from typing import Any

from app.game import actions as A
from app.game import ops
from app.game.errors import ActionError
from app.game.handlers.players import change_life
from app.game.ops import log, text
from app.game.rules_state import RulesState, capture, emit, track
from app.game.state import GameState, LogPart

_NOT_A_STEP = A.INTENT_TYPES | {"run_macro", "restore_state", "response_open"}


def apply_intent(state: GameState, a: A.Action) -> None:
    steps = getattr(a, "r", None)
    if not steps:
        raise ActionError("unresolved rules intent")
    replay_steps(state, steps)


def replay_steps(state: GameState, steps: list[dict[str, Any]]) -> None:
    """Apply recorded rules steps, with the same per-step bookkeeping the engine did."""
    from app.game.engine import HANDLERS  # the engine imports this module

    for payload in steps:
        step = A.parse_action(payload)
        if step.type in _NOT_A_STEP or step.type == "configure":
            raise ActionError("Invalid rules step")
        before = capture(state)
        HANDLERS[step.type](state, step)
        track(state, before)


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


def rules_damage(state: GameState, a: A.RulesDamage) -> None:
    # Damage is an event of its own (not "change life"): a player dealt damage also loses that
    # much life, a creature gets marked damage, a planeswalker loses loyalty. All of one step's
    # damage is dealt simultaneously (one event batch).
    for d in a.dealt:
        emit(state, "damage", object_id=d.target_object, card=d.target if d.target in state.cards else None,
             player=d.target if d.target in state.players else None, source=d.source, amount=d.amount, combat=a.combat)
    hurt = []
    for cid, n in a.creatures.items():
        card = ops.card(state, cid)
        card.damage += n
        hurt.append(card)
    for cid, n in a.wither.items():  # wither / infect (702.80, 702.90): -1/-1 counters instead of damage
        card = ops.card(state, cid)
        card.counters["-1/-1"] = card.counters.get("-1/-1", 0) + n
        hurt.append(card)
    walkers = []
    for cid, n in a.planeswalkers.items():
        card = ops.card(state, cid)
        left = card.counters.get("loyalty", 0) - n
        if left > 0:
            card.counters["loyalty"] = left
        else:
            card.counters.pop("loyalty", None)
        walkers.append(card)
    for hit in a.commander:
        p = state.players[hit.player]
        p.commander_damage[hit.commander] = p.commander_damage.get(hit.commander, 0) + hit.amount
    for pid, n in a.players.items():
        change_life(state, pid, state.players[pid].life - n)
    for pid, n in a.poison.items():  # infect: poison counters instead of life loss
        p = state.players[pid]
        p.resources["poison"] = p.resources.get("poison", 0) + n
    for pid, n in a.lifelink.items():
        change_life(state, pid, state.players[pid].life + n)
    parts = [text("First-strike combat damage: " if a.first_strike else "Combat damage: " if a.combat else "Damage: ")]
    pieces: list[list[LogPart]] = [[ops.pname(state, pid), text(f" takes {n}")] for pid, n in a.players.items()]
    pieces += [[ops.pname(state, pid), text(f" gets {n} poison")] for pid, n in a.poison.items()]
    if hurt:
        pieces.append([ops.group(state, hurt), text(" dealt damage")])
    if walkers:
        pieces.append([ops.group(state, walkers), text(" lose loyalty")])
    pieces += [[ops.pname(state, pid), text(f" gains {n} life (lifelink)")] for pid, n in a.lifelink.items()]
    for i, piece in enumerate(pieces or [[text("none")]]):
        parts += ([text("; ")] if i else []) + piece
    log(state, a.actor, a.ts, parts, kind="combat")


def rules_log(state: GameState, a: A.RulesLog) -> None:
    if a.fold:
        for entry in state.log[-a.fold:]:
            entry.folded = True
    parts = [text(a.text)]
    for cid in a.card_ids:
        if cid in state.cards:
            parts += [text(" "), ops.card_part(state, state.cards[cid])]
    log(state, a.actor, a.ts, parts, kind=a.kind)
