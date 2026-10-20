"""CR 701.67a, 118.3: waterbending paid during resolution.

A tapped artifact or creature pays for one generic mana. Affordability considers
which helpers remain available as mana sources, so one permanent cannot do both.
"""
from __future__ import annotations

from itertools import combinations
from typing import TYPE_CHECKING

from app.rules import costs as C
from app.rules import mana as M

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan


def mana(cost: C.AbilityCost, chosen: dict[int, list[str]]) -> M.ManaCost:
    n = sum(len(chosen.get(i, [])) for i, comp in cost.choices if comp.kind == C.WATERBEND)
    return M.parse_cost(cost.mana).plus_generic(-n)


def problem(plan: Plan, payer: str, source: CardInstance, cost: C.AbilityCost,
            chosen: dict[int, list[str]] | None) -> str | None:
    from app.rules import casting, cost_payment

    bending = [(i, comp) for i, comp in cost.choices if comp.kind == C.WATERBEND]
    if not bending:
        return None
    if chosen is not None:
        return None if casting.can_pay(plan.state, payer, mana(cost, chosen), plan.info,
                                      exclude=cost_payment.excluded(cost, source, chosen)) else "Not enough mana after waterbending"
    # Resolution supports a single waterbend part. With enough untapped helpers
    # it is free; otherwise enumerate the smaller group, retaining their mana options.
    i, comp = bending[0]
    helpers = cost_payment.candidates(plan, comp, payer, source)
    if len(helpers) >= comp.amount:
        return None
    for n in range(len(helpers) + 1):
        for group in combinations(helpers, n):
            picks = {i: list(group)}
            if casting.can_pay(plan.state, payer, mana(cost, picks), plan.info,
                               exclude=cost_payment.excluded(cost, source, picks)):
                return None
    return "Not enough mana or untapped artifacts and creatures to waterbend"
