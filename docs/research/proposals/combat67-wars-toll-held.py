"""Exact opponent all-if-one attack requirement uses native declaration completion."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics

TEXT = 'If a creature an opponent controls attacks, all creatures that opponent controls attack if able.'


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.kind != 'static' or ability.text != TEXT:
        return None
    from app.rules import selectors, statics

    return statics._definition(selectors.Selector(types=('Creature',), controller='opponent').key(), None, [],
                               rules=['attack_with_others'])
