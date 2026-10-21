"""CR 603.4, 400.7: mana actually added by this object's ability this turn.

Declining a may, countering the trigger, and adding zero mana do not close the gate.
The identity is the source object and printed ability index, independent of controller.
"""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics
    from app.rules.plan import Plan

CLAUSE = "if you haven't added mana with this ability this turn, "


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or CLAUSE not in ability.text:
        return None
    inner = scripts.define(replace(ability, text=ability.text.replace(CLAUSE, '', 1)), ch)
    if inner is None or inner.get('if') or len(inner.get('effects', [])) != 1 or inner['effects'][0].get('do') != 'add_mana':
        return None
    return {**inner, 'if': {'ability_no_mana': ability.index},
            'effects': [*inner['effects'], {'do': 'remember_ability_mana', 'index': ability.index}]}


def key(plan: Plan, ctx: dict[str, Any], index: int) -> str:
    return f"{ctx.get('source_object')}:{index}:mana:t{plan.state.turn.number}"


def holds(plan: Plan, ctx: dict[str, Any], index: int) -> bool:
    return not plan.rules.ability_uses.get(key(plan, ctx, index), 0)


def remember(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    if sum((ctx.get('_mana_added') or {}).values()) > 0:
        plan.rules.ability_uses[key(plan, ctx, e['index'])] = 1
    return True


PRIMITIVES = {'remember_ability_mana': remember}
