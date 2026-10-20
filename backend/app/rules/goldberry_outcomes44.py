"""Exact-kind movement and mandatory accepted-payment continuations."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'goldberry_outcome44'
RECEIPT = 'goldberry_payment44'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import language

    text = body.strip().replace('this creature', '~')
    modes = {
        'Move a counter of each kind not on ~ from another target permanent you control onto ~.': 'collect',
        'Move one or more counters from ~ onto another target permanent you control. If you do, draw a card.': 'pay',
    }
    mode = modes.get(text)
    if mode is None:
        return None
    target = language._target_key('another target permanent you control')
    if target is None:
        return None
    return ([{'do': STEP, 'mode': mode}], target, False)


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, counter_kinds, counter_moves, effects, prohibitions

    if e['mode'] == 'draw_if_started':
        receipt = counter_moves.CounterMoveReceipt.model_validate(
            ctx.get('counter_move_receipts', {}).get(RECEIPT, {}))
        # Actual removals prove this permissible mandatory payment STARTED.
        # This boolean is never interpreted as a numeric "counters moved".
        if receipt.removed:
            ctx['effects'][ctx['next']:ctx['next']] = [{'do': 'draw', 'who': 'you', 'n': 1}]
        return True
    own = plan.state.cards.get(ctx.get('source_card', ''))
    targets = effects._cards(plan, ctx, 'target')
    if (own is None or not own.zone.endswith(':battlefield')
            or plan.oid(own) != ctx.get('source_object') or len(targets) != 1):
        return True
    other = plan.state.cards[targets[0]]
    source, target = (other, own) if e['mode'] == 'collect' else (own, other)
    if not source.zone.endswith(':battlefield') or not target.zone.endswith(':battlefield') or source.id == target.id:
        return True
    have = {k: n for k, n in sorted(source.counters.items()) if n > 0
            and not prohibitions.cant_remove_counters(plan, source.id, k)
            and not prohibitions.cant_counters(plan, target.id, None, k)}
    if e['mode'] == 'collect':
        # Freeze the original kind difference before any removals or put replacements.
        have = {k: 1 for k in have if target.counters.get(k, 0) <= 0}
    if not have:
        return True
    source_ref, target_ref = context.ref_of(plan, source.id), context.ref_of(plan, target.id)
    if source_ref is None or target_ref is None:
        return True
    if e['mode'] == 'collect':
        return counter_moves.finish(plan, ctx, e, [source.id], target.id, have,
                                    source_refs=[source_ref], destination_ref=target_ref)
    move = {**e, 'receipt': RECEIPT, 'numeric': True}
    ctx['effects'][ctx['next']:ctx['next']] = [{'do': STEP, 'mode': 'draw_if_started'}]
    return counter_kinds.ask_amounts(plan, ctx, move, have, {'do': 'move', 'need': 1,
        'from': [source.id], 'to': target.id, 'source_refs': [source_ref.model_dump(mode='json')],
        'destination_ref': target_ref.model_dump(mode='json')})
