"""Exact self-replacement branches use one native resolution-time verdict."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

DARK = 'Dark Temper deals 2 damage to target creature. If you control a black permanent, destroy the creature instead.'
WILL = "Target creature gets +2/+2 until end of turn. If it's blocking, instead put two +1/+1 counters on it."
EIDOLON = "{R}: This creature gets +1/+0 until end of turn. If it's an Aura, enchanted creature gets +1/+0 until end of turn instead."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import conditions, scripts

    text = ability.text
    if (ability.kind, text) not in (('spell', DARK), ('spell', WILL), ('activated', EIDOLON)):
        return None
    alternate: dict[str, Any]
    if text == DARK:
        base = 'Dark Temper deals 2 damage to target creature.'
        condition = conditions.parse('you control a black permanent', objects=True)
        alternate = {'do': 'destroy', 'who': 'target'}
    elif text == WILL:
        base = 'Target creature gets +2/+2 until end of turn.'
        parsed = conditions.parse("it's a blocking creature", objects=True)
        condition = {**parsed, 'object': 'target'} if parsed is not None else None
        alternate = {'do': 'add_counters', 'who': 'target', 'kind': '+1/+1', 'n': 2}
    else:
        base = '{R}: This creature gets +1/+0 until end of turn.'
        condition = conditions.parse('~ is an Aura', objects=True)
        alternate = {'do': 'pump', 'who': 'host', 'p': 1, 't': 0}
    native = scripts.define(replace(ability, text=base), ch)
    if native is None or condition is None or len(native.get('effects') or []) != 1:
        return None
    verdict = 'conditional_instead59'
    return {**native, 'effects': [
        {'do': 'only_if', 'cond': condition, 'bind': verdict, 'skip': 1}, alternate,
        {'do': 'only_if', 'cond': {'flag': verdict, 'negate': True}, 'skip': 1},
        *native['effects']]}
