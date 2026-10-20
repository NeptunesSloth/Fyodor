"""As-cast abilities attached to the actual selected permission (601.2, 611.2)."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.permissions import Grant
    from app.rules.plan import Plan


def apply(spell: Characteristics, grant: Grant | None) -> Characteristics:
    if grant is None or not grant.spell_keywords:
        return spell
    from app.rules.oracle import parse_abilities

    extra = [ability for keyword in grant.spell_keywords for ability in parse_abilities(keyword.capitalize() + '.')]
    at = max([ability.index for ability in spell.abilities], default=99) + 1
    return replace(spell, abilities=(*spell.abilities, *(replace(ability, index=at + i) for i, ability in enumerate(extra))))


def retain(plan: Plan, card: CardInstance, grant: Grant | None) -> None:
    if grant is None or not grant.spell_keywords:
        return
    from app.rules import layers

    layers.add_effect(plan, affected=[plan.oid(card)], layer='6', source=None, controller=card.controller,
                      add_abilities=[keyword.capitalize() + '.' for keyword in grant.spell_keywords],
                      duration='permanent', label=grant.label)
