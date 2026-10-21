"""Declared-X mixed-counter cost on exactly one chosen permanent."""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.rules import costs as C

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan


def parse(part: str) -> C.CostComponent | None:
    if part != 'Remove X counters from an artifact or creature you control':
        return None
    key = C._selector('artifact or creature you control', zone='battlefield')
    assert key is not None
    return C.CostComponent(C.REMOVE_COUNTER, amount=0, counter=C.ANY_COUNTER, selector=key, x=True, text=part)


def one_holder_problem(plan: Plan, comp: C.CostComponent, card: CardInstance, player: str,
                       x: int | None, excluded: tuple[str, ...] = ()) -> str | None:
    if comp.kind != C.REMOVE_COUNTER or not comp.x or comp.counter != C.ANY_COUNTER or comp.among or comp.selector is None:
        return None
    from app.rules import cost_payment

    need = max(0, x or 0)
    holders = [cid for cid in cost_payment.candidates(plan, comp, player, card) if cid not in excluded]
    if not holders or max(cost_payment.removable_counters(plan, plan.state.cards[cid], comp.counter)
                          for cid in holders) < need:
        return f'You cannot remove {need} counters from one eligible permanent to pay this cost'
    return None
