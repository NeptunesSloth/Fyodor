"""Required alternatives of a cast offered during resolution (118.9, 608.2g).

Descriptors retain the alternative; ordinary native cost components choose and
pay it atomically with the spell's other costs. No separate prepayment occurs.
"""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.costs import AbilityCost
    from app.rules.plan import Plan


def textual_alternative(text: str) -> tuple[str, AbilityCost]:
    """Split one printed alternative into its mana and native nonmana payment.

    The latter joins total costs, so choices and life are paid once at 601.2h.
    """
    from app.rules import costs

    parsed = costs.parse_ability_cost(text)
    if parsed.unsupported or parsed.either or parsed.activation_only:
        raise ActionError('Unsupported casting alternative cost')
    return parsed.mana, replace(parsed, mana='', components=tuple(c for c in parsed.components if c.kind != costs.MANA))


def kind(effect: dict[str, Any]) -> str:
    value = effect.get('effect_alternative', '')
    if value not in ('', 'life_mv', 'discard'):
        raise ActionError('Unknown required casting alternative')
    if value and (effect.get('paid') or effect.get('effect_mana_cost')):
        raise ActionError('Only one alternative cost can be applied to a spell')
    return str(value)


def cost(effect: dict[str, Any], spell: Characteristics) -> AbilityCost:
    from app.rules import costs, permissions

    mode = kind(effect)
    if mode == 'life_mv':
        return permissions.life_cost(permissions.Grant('resolving', life_mv=True), spell) or costs.AbilityCost()
    if mode == 'discard':
        found = costs.parse_additional_cost('Discard a card')
        assert found is not None
        return found
    return costs.AbilityCost()


def problem(plan: Plan, player: str, card: CardInstance, spell: Characteristics, effect: dict[str, Any]) -> str | None:
    from app.rules import alt_costs, casting, costs

    if not kind(effect):
        return None
    combined = alt_costs.merged(costs.spell_additional_cost(spell.abilities), cost(effect, spell))
    return casting.additional_problem(plan, combined, card, player) if combined is not None else None
