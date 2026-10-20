"""Conditions on mana actually spent for one activated ability stack object."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_WORDING = re.compile(r'mana from a Treasure was spent to activate this ability|exactly (?P<n>\w+) colors of mana were spent to activate this ability',re.IGNORECASE)


def parse(text: str) -> dict[str, Any] | None:
    from app.rules.conditions import _num

    m=_WORDING.fullmatch(text)
    if m is None:
        return None
    if m['n'] is None:
        return {'activation_payment':{'tag':'Treasure'}}
    n=_num(m['n'])
    return {'activation_payment':{'colors':n}} if n is not None else None


def refusal_text(text: str) -> str:
    """Exempt only clauses whose exact condition is modeled, retaining other refusals."""
    return _WORDING.sub(lambda m:'supported payment condition' if parse(m[0]) else m[0],text)


def holds(plan: Plan, ctx: dict[str, Any], need: dict[str, Any]) -> bool:
    if ctx.get('kind')!='activated':
        return False
    stack_id=ctx.get('stack_id')
    if not stack_id or stack_id not in plan.state.cards:
        return False
    record=plan.rules.payments.get(plan.oid(stack_id))
    if record is None or not record.mana_known:
        return False
    if need.get('tag') is not None:
        return any(need['tag'] in tags for tags in record.mana_tags)
    return sum(record.mana_spent.get(color,0)>0 for color in 'WUBRG')==need['colors']
