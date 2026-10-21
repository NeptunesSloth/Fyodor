"""Aragorn chooses native keyword counters and copies each proven kind once."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

FIRST = ('Whenever the Ring tempts you, if you chose a creature other than ~ as your Ring-bearer, '
         'put your choice of a counter from among first strike, vigilance, deathtouch, and lifelink on ~.')
SECOND = 'Whenever you put one or more counters on ~, put one of each of those kinds of counters on up to one other target creature.'


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if ability.kind != 'triggered' or text not in (FIRST, SECOND):
        return None
    if text == FIRST:
        return scripts.define(replace(ability, text=text.replace(
            'a counter from among first strike, vigilance, deathtouch, and lifelink',
            'a first strike counter, a vigilance counter, a deathtouch counter, or a lifelink counter')), ch)
    native = scripts.define(replace(ability, text=text.replace('one of each of those kinds of counters', 'a +1/+1 counter')), ch)
    if native is None:
        return None
    return {**native, 'effects': [
        {'do': 'ring_counter_kinds67', 'who': effect['who']} if effect['do'] == 'add_counters' else effect
        for effect in native['effects']]}


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects
    from app.rules.counter_receipts import CounterPlacement

    kinds = sorted({p.kind for raw in (ctx.get('event') or {}).get('counter_placements') or []
                    if (p := CounterPlacement.model_validate(raw)).amount > 0})
    if not kinds:
        return True
    return effects.add_counters(plan, ctx, {'do': 'add_counters', 'who': e['who'],
                                          'kind': kinds[0], 'n': 1,
                                          'also': [{'kind': kind, 'n': 1} for kind in kinds[1:]]})


PRIMITIVES = {'ring_counter_kinds67': run}
