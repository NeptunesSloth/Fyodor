"""A damage threshold is tested on one complete simultaneous recipient event."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = 'Whenever this creature is dealt 3 or more damage, investigate.'


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or ability.text != TEXT:
        return None
    native = scripts.define(replace(ability, text='Whenever this creature is dealt damage, investigate.'), ch)
    if native is None or native.get('cond', {}).get('event') != 'dealt_damage':
        return None
    return {**native, 'cond': {**native['cond'], 'damage_at_least': 3}}


def amounts(events: list[Any]) -> dict[tuple[int, str], int]:
    totals: dict[tuple[int, str], int] = {}
    for event in events:
        if event.kind == 'damage' and not event.manual and event.object_id:
            key = (event.batch, event.object_id)
            totals[key] = totals.get(key, 0) + max(0, event.amount)
    return totals


def matches(cond: dict[str, Any], fact: Any) -> bool:
    minimum = cond.get('damage_at_least')
    if minimum is None:
        return True
    if cond.get('event') != 'dealt_damage' or cond.get('subject') != 'self':
        return False
    total = fact[4].get('simultaneous_amount')
    return total is not None and int(total) >= int(minimum)
