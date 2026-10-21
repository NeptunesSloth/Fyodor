"""An exact split-line damage rider uses the resolving spell's native damage receipts."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

MAIN = ('~ deals 2 damage to target creature or planeswalker. If this spell was kicked, '
        'instead it deals 3 damage to that permanent and you scry 1.')
RIDER = 'If a permanent dealt damage by ~ would die this turn, exile it instead.'


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if text not in (MAIN, RIDER):
        return None
    paired = {scripts.self_text(a.text, ch.name): a for a in ch.abilities}
    if MAIN not in paired or RIDER not in paired:
        return None
    first = paired[MAIN]
    native = scripts.define(replace(first, text=first.text +
        ' If a permanent dealt damage this way would die this turn, exile it instead.'), ch)
    if native is None:
        return None
    if text == MAIN:
        return native
    return {'kind': 'spell', 'effects': [], 'target': None, 'merged_into': first.index}
