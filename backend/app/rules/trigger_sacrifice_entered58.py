"""Mandatory sacrifice receipts gate untargeted effects on the original entering object."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

PERIL = 'When a nonblack creature enters, sacrifice this enchantment. If you do, destroy that creature.'
SCOUT = ('When another creature enters, sacrifice this creature. If you do, this creature deals 4 damage '
         'to that creature.')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or ability.text not in (PERIL, SCOUT):
        return None
    native = scripts.define(replace(ability, text=ability.text.split(', sacrifice ', 1)[0] + ', you gain 1 life.'), ch)
    if native is None:
        return None
    text = ('Sacrifice ~. If you do, destroy target creature.' if ability.text == PERIL else
            'Sacrifice ~. If you do, ~ deals 4 damage to target creature.')
    parsed = scripts.parse_effects(text)
    if parsed is None:
        return None
    sacrifice, gate, effect = parsed[0]
    return {**native, 'effects': [sacrifice, gate, {**effect, 'who': 'ref:event'}]}
