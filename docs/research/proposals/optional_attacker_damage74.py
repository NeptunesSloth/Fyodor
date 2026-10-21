"""An exact optional damage instruction uses the native attacking event source."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if text != ('Whenever a creature you control with a +1/+1 counter on it attacks, you may have that creature '
                'deal 1 damage to target player or planeswalker.'):
        return None
    return scripts.define(replace(ability, text=text.replace('have that creature deal', 'have it deal')), ch)
