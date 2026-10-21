"""Copy the actual committed counter packet carried by a native trigger event."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

BOLD = ('Whenever an opponent puts one or more counters on a creature they control, '
        'they put the same number and kind of counters on ~.')
MARVEL = ("Whenever you put one or more counters on another creature, if it's not a Kree, "
          'you may put the same number and kind of counters on ~.')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if ability.kind != 'triggered' or text not in (BOLD, MARVEL):
        return None
    if text == BOLD:
        native = text.replace('they put the same number and kind of counters', 'put a +1/+1 counter')
    elif text == MARVEL:
        native = text.replace('the same number and kind of counters', 'a +1/+1 counter')
    found = scripts.define(replace(ability, text=native), ch)
    if found is None:
        return None
    rewritten = []
    for effect in found['effects']:
        if effect['do'] == 'add_counters':
            effect = {'do': 'event_counter_packet50', 'who': effect['who'],
                      **({'event_actor': True} if text == BOLD else {})}
        rewritten.append(effect)
    return {**found, 'effects': rewritten}


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects
    from app.rules.counter_receipts import CounterPlacement

    event = ctx.get('event') or {}
    actor = event.get('actor')
    if e.get('event_actor') and actor not in plan.live():
        return True
    totals: dict[str, int] = {}
    for raw in (ctx.get('event') or {}).get('counter_placements') or []:
        placement = CounterPlacement.model_validate(raw)
        if placement.amount > 0:
            totals[placement.kind] = totals.get(placement.kind, 0) + placement.amount
    if not totals:
        return True  # Legacy saves contain no proven packet; never infer one from the current board.
    kinds = [{'kind': kind, 'n': n} for kind, n in sorted(totals.items())]
    return effects.add_counters(plan, ctx, {'do': 'add_counters', 'who': e['who'],
                                          **kinds[0], 'also': kinds[1:],
                                          **({'by': f'player:{actor}'} if e.get('event_actor') else {})})


PRIMITIVES = {'event_counter_packet50': run}
