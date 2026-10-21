"""Explicit ordinary two-color hybrid power-up reductions before generic modifiers."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.rules import mana as M

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText
    from app.rules.plan import Plan


def readable(ch: Characteristics, mana: str | None) -> bool:
    own, due = M.parse_cost(ch.mana_cost), M.parse_cost(mana)
    if (len(own.hybrid) != 1 or len(due.hybrid) not in (1, 2) or own.colored or due.colored
            or own.x or due.x or own.phyrexian or due.phyrexian or own.unsupported or due.unsupported):
        return False
    hybrid = own.hybrid[0]
    return (len(hybrid) == 2 and len(set(hybrid)) == 2 and all(c in M.COLORS for c in hybrid)
            and all(slot == hybrid for slot in due.hybrid))


def reduced_costs(ch: Characteristics, mana: str) -> list[str]:
    from app.rules import spell_cost_stages

    own, due = M.parse_cost(ch.mana_cost), M.parse_cost(mana)
    costs: dict[str, None] = {}
    for due_choice in spell_cost_stages.variants(due):
        concrete_due = spell_cost_stages.concrete(due, due_choice)
        for own_choice in spell_cost_stages.variants(own):
            concrete_own = spell_cost_stages.concrete(own, own_choice)
            colored = list(concrete_due.colored)
            generic = max(0, concrete_due.generic - concrete_own.generic)
            for color in concrete_own.colored:
                if color in colored:
                    colored.remove(color)
                else:
                    generic = max(0, generic - 1)
            text = M.ManaCost(generic, tuple(sorted(colored, key=M.COLORS.index))).text()
            costs.setdefault(text, None)
    return list(costs)


def alternatives(state: GameState | None, card: CardInstance | None, ch: Characteristics,
                 ability: AbilityText) -> list[AbilityText] | None:
    from app.rules import power_up

    if (state is None or card is None or ability.power_up_prepared or not ability.text.startswith(power_up.PREFIX)
            or not readable(ch, ability.cost) or not power_up.entered_this_turn(state, card)):
        return None
    return [replace(ability, cost=cost, text=power_up.PREFIX + cost + ':' + ability.text.partition(':')[2],
                    power_up_prepared=True) for cost in reduced_costs(ch, ability.cost or '')]


def source_receipt(plan: Plan, card: CardInstance, ch: Characteristics, ability: AbilityText) -> dict[str, Any]:
    from app.game.rules_state import ObjectRef

    return {'source': ObjectRef(card=card.id, object_id=plan.oid(card), zone=card.zone).model_dump(mode='json'),
            'mana_cost': ch.mana_cost, 'index': ability.index, 'text': ability.text, 'cost': ability.cost}


def guard_source(plan: Plan, raw: dict[str, Any]) -> None:
    from app.game.errors import ActionError
    from app.game.rules_state import ObjectRef
    from app.rules import power_up

    ref = ObjectRef.model_validate(raw['source'])
    card = plan.state.cards.get(ref.card)
    if card is None or plan.oid(card) != ref.object_id or card.zone != ref.zone:
        raise ActionError('The power-up source is no longer the original object')
    if not power_up.entered_this_turn(plan.state, card):
        raise ActionError('The power-up reduction no longer applies this turn')
    ch = plan.ch(card)
    ability = next((a for a in ch.abilities if a.index == raw['index']), None)
    if (ch.mana_cost != raw['mana_cost'] or ability is None or ability.text != raw['text'] or ability.cost != raw['cost']):
        raise ActionError('The power-up cost choice no longer describes that ability')
