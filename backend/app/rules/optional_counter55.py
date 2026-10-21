"""Native source-counter tokens can pay a bounded optional removal cost."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.rules import cost_payment, costs
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.costs import AbilityCost, CostComponent
    from app.rules.plan import Plan


def component(comp: CostComponent) -> bool:
    return (comp.kind == costs.REMOVE_COUNTER and comp.counter == costs.ANY_COUNTER
            and comp.selector is None and comp.amount == 1 and not comp.x and not comp.among and not comp.more)


def allowed(cost: AbilityCost) -> bool:
    return len(cost.components) == 1 and component(cost.components[0])


def validate(plan: Plan, source: CardInstance, comp: CostComponent, chosen: list[str], used: set[str]) -> bool:
    tokens = cost_payment.counter_tokens(plan, [source.id])
    return len(chosen) == comp.amount and len(set(chosen)) == len(chosen) and all(t in tokens and t not in used for t in chosen)


def choose(plan: Plan, ctx: dict[str, Any], opt: dict[str, Any], cost: AbilityCost, i: int,
           comp: CostComponent, source: CardInstance, used: set[str]) -> list[str] | None:
    from app.rules import optional_payment

    if source.id not in plan.state.cards or not source.zone.endswith(':battlefield') or plan.oid(source) != ctx.get('source_object'):
        return []
    tokens = {t: v for t, v in cost_payment.counter_tokens(plan, [source.id]).items() if t not in used}
    if len(tokens) < comp.amount:
        return []  # The ordinary final validation declines the now-unpayable cost.
    if len(set(tokens.values())) == 1:
        return list(tokens)[:comp.amount]
    decide(plan, player=opt['payer'], kind='choose_cards',
           prompt=f"{ctx.get('name') or 'It'}: choose a counter to remove, or none to decline",
           options=[DecisionOption(id=t, label=f"{kind} counter on {source.name or 'it'}", card_id=cid)
                    for t, (cid, kind) in tokens.items()], min_choices=0, max_choices=comp.amount,
           resume=optional_payment._resume(ctx, opt, cost, component=i, amount=comp.amount, counter_pick55=True),
           source=source)
    return None
