"""A choice between a spell's additional costs (wave 6E): "As an additional cost to cast this spell, sacrifice an artifact
or discard a card." (Demand Answers), "… discard a card or pay 3 life." (Bitter Triumph), "… sacrifice a creature or pay
{3}{B}." (Eaten Alive).

601.2b: the caster announces which additional cost they intend to pay as the spell is cast, before its targets (601.2c);
601.2f: the chosen one is part of the total cost (a mana side adds to it like kicker, 118.8, before increases and
reductions); 601.2h: it's paid with the rest; 118.3: a side whose objects aren't there can't be chosen. When only one
side can be paid it is taken without asking. The choice is recorded on the cast intent as the cost choice
``costs.EITHER_SLOT`` ("either:<i>"), so a later decision of the same cast (targets, which objects pay) resumes with it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.game import actions as A
from app.game.errors import ActionError
from app.game.rules_state import DecisionOption
from app.rules import costs as C
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

WAITING = C.AbilityCost(unsupported=("waiting",))  # (a sentinel: the caster is being asked)


def problem(plan: Plan, cost: C.AbilityCost, card: CardInstance, player: str) -> str | None:
    """Why no side of the choice can be paid now (the first side's reason), or None."""
    from app.rules.casting import additional_problem

    reasons = [additional_problem(plan, side, card, player) for side in cost.either]
    return None if any(r is None for r in reasons) else reasons[0]


def announce(plan: Plan, a: A.CastSpell, card: CardInstance, ch: Characteristics) -> C.AbilityCost | None:
    """The side of the spell's additional cost the caster announced (601.2b): None when the spell has no such choice,
    ``WAITING`` while they're asked."""
    from app.rules.casting import additional_problem

    cost = C.spell_additional_cost(ch.abilities)
    if cost is None or not cost.either:
        return None
    sides = cost.either
    given = [c for c in a.cost_choices if c.component == C.EITHER_SLOT]
    if given:
        picked = given[-1].cards
        index = int(picked[0].split(":", 1)[1]) if len(picked) == 1 and picked[0].startswith("either:") \
            and picked[0].split(":", 1)[1].isdigit() else -1
        if not 0 <= index < len(sides):
            raise ActionError("Choose one of the spell's additional costs")
        why = additional_problem(plan, sides[index], card, plan.actor)
        if why:
            raise ActionError(why)
        return sides[index]
    payable = [i for i, side in enumerate(sides) if additional_problem(plan, side, card, plan.actor) is None]
    if not payable:
        raise ActionError(additional_problem(plan, sides[0], card, plan.actor) or "You can't pay its additional cost")
    if len(payable) == 1:  # (118.3: the other can't be paid — nothing to choose)
        a.cost_choices = [*a.cost_choices, A.CostChoice(component=C.EITHER_SLOT, cards=[f"either:{payable[0]}"])]
        return sides[payable[0]]
    decide(plan, player=plan.actor, kind="choose_cards",
           prompt=f"{ch.name or 'It'}: choose its additional cost (601.2b), or none to cancel",
           options=[DecisionOption(id=f"either:{i}", label=C.either_label(sides[i])) for i in payable],
           min_choices=0, max_choices=1,
           resume={"step": "ability_cost", "component": C.EITHER_SLOT, "amount": 1,
                   "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"})},
           source=card)
    return WAITING
