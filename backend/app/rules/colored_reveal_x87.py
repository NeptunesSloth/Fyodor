"""X colored hand-card reveals use the native announced-X activation cost receipt."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.rules.costs import CostComponent

_COLORED_X = re.compile(r'^Reveal X (?P<color>white|blue|black|red|green) cards from your hand$')


def component(part: str) -> CostComponent | None:
    from app.rules import costs

    match = _COLORED_X.fullmatch(part)
    if match is None:
        return None
    key = costs._selector(match['color'] + ' cards', zone='hand')
    return costs.CostComponent('REVEAL_FROM_HAND', amount=0, selector=key, x=True, text=part) if key else None
