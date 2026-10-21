"""Bounded server-only numeric values fixed during native spell announcement."""
from __future__ import annotations

from typing import Any

from app.game.errors import ActionError
from app.rules.plan import Plan


def capture(plan: Plan, definition: dict[str,Any] | None) -> int | None:
    if definition is None or definition.get('x_as_cast')!='greatest_own_power':
        return None
    if plan.locked_cast_greatest_power is not None:
        return plan.locked_cast_greatest_power
    from app.rules import selectors, values

    return values.evaluate(plan,{'controller':plan.actor},
                           {'max':'power','of':selectors.Selector(types=('Creature',),controller='you',zones=('battlefield',)).key()})


def stack_x(definition: dict[str,Any] | None, snapshot: int | None, announced: int | None) -> int | None:
    if definition is None or definition.get('x_as_cast')!='greatest_own_power':
        return announced
    if snapshot is None:
        raise ActionError('The saved spell has no as-cast power receipt; resolve this legacy spell by hand')
    return snapshot
