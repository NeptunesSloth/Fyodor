"""Bound cast-spell references retain native non-target counter semantics."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics

TEXTS = frozenset({
    'When an opponent casts a spell, sacrifice this enchantment and counter that spell.',
    'When a player casts a spell, sacrifice this enchantment and counter that spell.',
    'Whenever a player casts an enchantment spell, counter it.',
})


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.kind != 'triggered' or ability.text not in TEXTS:
        return None
    from app.rules import scripts

    text = ability.text.replace(' and counter that spell', '. Counter that spell').replace('counter it.', 'counter that spell.')
    return scripts.define(replace(ability, text=text), ch)
