"""Exile original library objects until their cumulative mana value reaches a threshold."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import ObjectRef
from app.rules import context

if TYPE_CHECKING:
    from app.rules.plan import Plan

_TASHA = "Each opponent exiles cards from the top of their library until that player has exiled cards with total mana value 20 or greater."
_DREAM = "Each opponent exiles cards from the top of their library until they have exiled cards with total mana value 5 or greater this way. Until end of turn, you may cast cards exiled this way without paying their mana costs."
_BINDING = 'threshold_exiled'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = body.strip().casefold()
    if text not in (_TASHA.casefold(), _DREAM.casefold()):
        return None
    dream = text == _DREAM.casefold()
    effects: list[dict[str, Any]] = [{'do': 'exile_mv_threshold', 'threshold': 5 if dream else 20, 'as': _BINDING}]
    if dream:
        effects.append({'do': 'grant_play', 'who': 'ref:' + _BINDING, 'play': False, 'cast': True,
                        'until': 'end_of_turn', 'free': True, 'from_exile': True})
    return effects, None, False


def exile(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    original: list[dict[str, Any]] = []
    for pid in plan.apnap():
        if pid == ctx['controller']:
            continue
        total = 0
        while total < e['threshold'] and (library := plan.state.zones.get(f'{pid}:library', [])):
            before = context.ref_of(plan, library[0])
            effects.exile_top(plan, ctx, {'do': 'exile_top', 'player': 'player:' + pid, 'n': 1, 'as': 'threshold_one'})
            moved = (context.refs(ctx).get('threshold_one') or {}).get('objects', [])
            for raw in moved:
                card = context._same(plan, ObjectRef.model_validate(raw))
                if card is not None and card.zone.endswith(':exile'):
                    original.append(raw)
                    total += int(plan.ch(card).mana_value)
            if before is not None and context._same(plan, before) is not None:
                break
    context.refs(ctx).pop('threshold_one', None)
    context.refs(ctx)[e['as']] = {'kind': 'objects', 'objects': original}
    return True


PRIMITIVES = {'exile_mv_threshold': exile}
