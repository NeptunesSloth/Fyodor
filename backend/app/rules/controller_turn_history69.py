"""Exact control-acquisition history and continuous-control sacrifice scope."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.rules_state import TurnLog
    from app.rules.plan import Plan

MAD = "At the beginning of your end step, if ~ didn't attack or come under your control this turn, sacrifice it."
ERG = "At the beginning of your end step, if ~ didn't attack this turn, it deals 2 damage to you unless it came under your control this turn."
TWILIGHT = ("At the beginning of each player's end step, if no creatures attacked this turn, that player "
            'sacrifices a creature of their choice that they controlled since the beginning of the turn.')
EXTRA = 'controlled_since_turn_start69'


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    text = scripts.self_text(ability.text, ch.name)
    if ability.kind != 'triggered' or text not in (MAD, ERG, TWILIGHT):
        return None
    if text == TWILIGHT:
        base = text.replace(' that they controlled since the beginning of the turn', '')
    else:
        base = ("At the beginning of your end step, if ~ didn't attack this turn, "
                + ('sacrifice it.' if text == MAD else 'it deals 2 damage to you.'))
    native = scripts.define(replace(ability, text=base), ch)
    if native is None:
        return None
    effects = native['effects']
    if text == TWILIGHT:
        edict = effects[-1]
        sel = selectors.from_key(edict['sel'])
        return {**native, 'effects': [*effects[:-1], {**edict, 'sel': replace(sel, extras=(*sel.extras, EXTRA)).key()}]}
    exception = {'not': {'history': 'control_acquired69'}}
    if text == MAD:
        cond = {'all': [native['if'], exception]}
        return {**native, 'if': cond, 'effects': [{**effects[0], 'cond': cond}, *effects[1:]]}
    return {**native, 'effects': [*effects[:-1], {'do': 'only_if', 'cond': exception, 'skip': 1}, effects[-1]]}


def note(events: list[Any], log: TurnLog, turn: int) -> None:
    from app.game.rules_state import TurnFact

    for event in events:
        if (event.turn == turn and event.kind == 'designation' and event.counter == 'control'
                and event.player and event.object_id):
            log.facts.append(TurnFact(kind='control_acquired', player=event.player, object_id=event.object_id))


def acquired(plan: Plan, ctx: dict[str, Any], log: TurnLog) -> bool:
    from app.rules import history

    oid = history._source_object(plan, ctx)
    player = ctx['controller']
    return oid is not None and (
        any(entry.object_id == oid and entry.controller == player for entry in log.entered)
        or any(fact.kind == 'control_acquired' and fact.object_id == oid and fact.player == player for fact in log.facts))


def continuous(plan: Plan, card: Any) -> bool:
    mark = plan.rules.controlled_since.get(card.id)
    if mark is None or mark.controller != card.controller:
        return False
    since = mark.turn if mark.turn > 0 else getattr(mark, 'observed_from_turn', None)
    return since is not None and since < plan.state.turn.number
