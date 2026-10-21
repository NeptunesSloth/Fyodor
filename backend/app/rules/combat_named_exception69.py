"""Akron's explicit named-creature exception is a native filtered attack prohibition."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics

TEXT = "Except for creatures named Akron Legionnaire and artifact creatures, creatures you control can't attack."


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.kind != 'static' or ability.text != TEXT:
        return None
    from app.rules import selectors, statics

    who = selectors.Selector(types=('Creature',), not_types=('Artifact',), controller='you',
                             extras=('not_name:Akron Legionnaire',)).key()
    return statics._definition(who, None, [], rules=['cant_attack'])
