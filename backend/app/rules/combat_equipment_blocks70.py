"""Equipment-derived additional blocks are read when a declaration is checked."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics
    from app.rules.plan import Plan

PREFIX = 'block_extra_equipment70:'
TEXT = 'This creature can block an additional creature each combat for each Equipment attached to this creature.'


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.kind != 'static' or ability.text != TEXT:
        return None
    from app.rules import statics

    return statics._definition('self', None, [], rules=[PREFIX + '@src'])


def extra(plan: Plan, ch: Characteristics) -> int:
    result = 0
    for rule in ch.imposed:
        if not rule.startswith(PREFIX):
            continue
        source = plan.state.cards.get(rule[len(PREFIX):])
        if source is None or not source.zone.endswith(':battlefield'):
            continue
        result += sum(c.zone.endswith(':battlefield') and c.attached_to == source.id and plan.in_game(c)
                      and 'Equipment' in plan.ch(c).subtypes for c in plan.state.cards.values())
    return result
