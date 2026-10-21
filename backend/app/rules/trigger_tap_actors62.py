"""Singular instructed taps retain the native event actor and per-object frequency."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

LEAD = 'Whenever you tap an untapped creature an opponent controls, '
TEXTS = (LEAD + 'put a +1/+1 counter on target creature you control.',
         LEAD + 'this creature gets +2/+1 until end of turn.')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or ability.text not in TEXTS:
        return None
    text = ability.text.replace(LEAD, 'Whenever you tap one or more untapped creatures your opponents control, ', 1)
    native = scripts.define(replace(ability, text=text), ch)
    if native is None:
        return None
    cond = native.get('cond') or {}
    if cond.get('event') != 'tapped' or cond.get('tapper') != 'you' or not cond.get('aggregate'):
        return None
    return {**native, 'cond': {**cond, 'aggregate': False}}
