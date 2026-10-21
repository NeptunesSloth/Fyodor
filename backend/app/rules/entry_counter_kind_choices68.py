"""Freeze the distinct counter kinds once, then use native optional choices per kind."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

TEXT = ('When ~ enters, for each kind of counter on permanents you control, you may put your choice '
        'of a +1/+1 counter or a counter of that kind on ~.')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or scripts.self_text(ability.text, ch.name) != TEXT:
        return None
    native = scripts.define(replace(ability, text='When ~ enters, put a +1/+1 counter on ~.'), ch)
    return {**native, 'effects': [{'do': 'entry_counter_kind_choices68'}]} if native is not None else None


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, prohibitions, selectors

    source = effects._cards(plan, ctx, 'self')
    if len(source) != 1:
        return True
    mine = selectors.Selector(types=selectors.PERMANENT_TYPES, controller='you')
    kinds = sorted({kind for cid in selectors.candidates(plan, mine, ctx['controller'])
                    for kind, amount in plan.state.cards[cid].counters.items() if amount > 0})
    queued = []
    for kind in kinds:
        options = []
        for choice in dict.fromkeys(('+1/+1', kind)):
            if not prohibitions.cant_counters(plan, source[0], None, choice):
                options.append({'label': f'Put a {choice} counter on it', 'effects': [
                    {'do': 'add_counters', 'who': 'self', 'kind': choice, 'n': 1}]})
        if options:
            options.append({'label': 'Do not put a counter on it', 'effects': []})
            queued.append({'do': 'pick_one', 'options': options})
    at = ctx['next']
    ctx['effects'] = [*ctx['effects'][:at], *queued, *ctx['effects'][at:]]
    return True


PRIMITIVES = {'entry_counter_kind_choices68': run}
