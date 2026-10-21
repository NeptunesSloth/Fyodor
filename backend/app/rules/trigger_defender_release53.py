"""Guardian of the Ages permanently exchanges defender for trample after attack."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = ('When a creature attacks you or a planeswalker you control, if this creature has defender, '
        'it loses defender and gains trample.')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or ability.text != TEXT:
        return None
    native = scripts.define(replace(ability, text=TEXT.replace(
        'it loses defender and gains trample.', 'this creature gains trample until end of turn.')), ch)
    if native is None:
        return None
    gate, grant = native['effects']
    if gate.get('do') != 'only_if' or grant.get('do') != 'grant':
        return None
    return {**native, 'effects': [gate, {**grant, 'remove': ['defender'], 'duration': 'permanent'}]}
