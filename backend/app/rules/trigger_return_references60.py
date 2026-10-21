"""Exact hand ownership and original attacking-creature references."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

HAMMER = "Whenever equipped creature attacks, you may return a land you control to its owner's hand. If you do, the creature gets +2/+2 until end of turn."
MAGE = 'Whenever a permanent is returned to your hand, you may pay {1}. If you do, draw a card.'


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or ability.text not in (HAMMER, MAGE):
        return None
    text = (HAMMER.replace('the creature gets', 'equipped creature gets') if ability.text == HAMMER else
            'Whenever a permanent you own is returned to hand, you may pay {1}. If you do, draw a card.')
    native = scripts.define(replace(ability, text=text), ch)
    if native is None:
        return None
    if ability.text == HAMMER:
        effects = native.get('effects') or []
        if len(effects) != 3 or effects[-1].get('do') != 'pump':
            return None
        # "The creature" attacked. Equipment may have moved before resolution.
        native = {**native, 'effects': [*effects[:-1], {**effects[-1], 'who': 'ref:event'}]}
    return native
