"""CR 118.3, 601.2b, 602.2b: announce a mana-or-energy activation cost.

Each side is a complete cost. Taxes, reductions, timing and payment use the
ordinary activation path after choosing; no resources are paid at the prompt.
"""
from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.game.actions import ActivateAbility
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText
    from app.rules.plan import Plan

_SYMBOLS = r"(?:\{(?:\d+|[WUBRGCE])\})+"
_EITHER = re.compile(rf"^(?:Pay )?({_SYMBOLS}) or (?:[Pp]ay )?({_SYMBOLS})$")


def sides(text: str) -> list[str] | None:
    m = _EITHER.fullmatch(text)
    if m is None:
        return None
    return ['Pay ' + x if '{E}' in x else x for x in m.groups()]


def reconfigure_cost(line: str) -> str | None:
    from app.rules.costs import parse_ability_cost

    m = re.fullmatch(r'Reconfigure(?: (' + _SYMBOLS + r')|—(.+))', line.rstrip('.'), re.IGNORECASE)
    if m is None:
        return None
    text = m[1] or m[2]
    parsed = parse_ability_cost(text)
    return text if not parsed.unsupported and (parsed.components or parsed.either) else None


def with_cost(ability: AbilityText, text: str) -> AbilityText:
    return replace(ability, cost=text, text=text + ':' + ability.text.partition(':')[2])


def announce(plan: Plan, a: ActivateAbility, card: CardInstance, ch: Characteristics,
             ability: AbilityText) -> AbilityText | None:
    from app.game.errors import ActionError
    from app.game.rules_state import DecisionOption
    from app.rules import casting, costs
    from app.rules.plan import decide

    choices = sides(ability.cost or '')
    if choices is None:
        return ability
    made = [with_cost(ability, side) for side in choices]
    given = next((c.cards for c in a.cost_choices if c.component == costs.EITHER_SLOT), None)
    if given is not None:
        index = int(given[0][7:]) if len(given) == 1 and given[0].startswith('either:') and given[0][7:].isdigit() else -1
        if not 0 <= index < len(made):
            raise ActionError('Choose one of the activation costs')
        return made[index]
    offered = [i for i, candidate in enumerate(made) if casting.ability_problem(
        plan.state, plan.actor, card, ch, candidate,
        casting.ability_cost(ch, candidate, state=plan.state, card=card, info=plan.info),
        info=plan.info, plan=plan) is None]
    if not offered:
        raise ActionError("You can't pay either activation cost")
    if len(offered) == 1:
        from app.game.actions import CostChoice

        a.cost_choices = [*a.cost_choices, CostChoice(component=costs.EITHER_SLOT, cards=[f'either:{offered[0]}'])]
        return made[offered[0]]
    decide(plan, player=plan.actor, kind='choose_cards', prompt=f'{ch.name}: choose its activation cost, or none to cancel',
           options=[DecisionOption(id=f'either:{i}', label=choices[i]) for i in offered], min_choices=0, max_choices=1,
           resume={'step': 'ability_cost', 'component': costs.EITHER_SLOT, 'amount': 1,
                   'intent': a.model_dump(mode='json', exclude={'r', 'actor', 'ts'})}, source=card)
    return None
