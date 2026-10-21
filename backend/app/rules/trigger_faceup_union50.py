"""The exact Detective entry/face-up union retains its native event object."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = 'Whenever a Detective you control enters or is turned face up, put a +1/+1 counter on it.'


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import events, scripts

    if ability.kind != 'triggered' or ability.text != TEXT:
        return None
    native = scripts.define(replace(ability, text=TEXT.replace('enters or is turned face up', 'enters')), ch)
    clauses = [events.parse_condition(text) for text in
               ['a Detective you control enters', 'a Detective you control is turned face up']]
    if native is None or any(clause is None for clause in clauses):
        return None
    return {**native, 'cond': {'event': 'either', 'conds': clauses}}
