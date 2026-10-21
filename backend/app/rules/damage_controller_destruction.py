"""CR 120.8, 400.7, 608.2h: destroy permanents of players damaged by the source.

The source's object identity is captured on activation. Only positive, actually dealt
combat damage this turn qualifies; membership and characteristics are read on resolution.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.rules import selectors

if TYPE_CHECKING:
    from app.rules.plan import Plan

_WORDING = re.compile(
    r'^destroy (?:each|all) (?P<what>.+?) whose controller was dealt '
    r'(?P<combat>combat )?damage by (?:~|this creature|this permanent) this turn$')


def definition(m: re.Match[str]) -> tuple[list[dict[str, Any]], None]:
    from app.rules.scripts import _NoMatch

    sel = selectors.parse(m['what'])
    if sel is None or sel.player is not None or sel.card or sel.zones != ('battlefield',):
        raise _NoMatch
    return [{'do': 'destroy_damage_controllers', 'selector': sel.key(), 'combat': bool(m['combat'])}], None


def destroy(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects, history

    damaged = {f.player for f in history.log_for(plan, False).facts
               if f.kind == 'damage' and f.amount > 0 and f.object_id == ctx.get('source_object')
               and (f.combat or not e['combat'])}
    sel = selectors.from_key(e['selector'])
    sel = selectors.replace(sel, compare=tuple((stat, op, int(ctx.get('x') or 0) if n == selectors.X_VALUE else n)
                                               for stat, op, n in sel.compare))
    cards = [cid for cid in selectors.candidates(plan, sel, ctx['controller'], ctx.get('source_card'))
             if plan.state.cards[cid].controller in damaged]
    # Use the ordinary simultaneous destruction pipeline (indestructible,
    # regeneration, replacements, and this-way bindings), without targets.
    context.bind_objects(plan, ctx, 'damage_controllers', cards)
    return effects.destroy(plan, ctx, {**e, 'who': 'ref:damage_controllers'})


TEMPLATES = [(_WORDING, definition)]
PRIMITIVES = {'destroy_damage_controllers': destroy}
