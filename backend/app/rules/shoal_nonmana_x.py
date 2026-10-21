"""Exact native nonmana-X alternative-cost recipe."""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.rules import alt_costs, costs


@dataclass(frozen=True)
class NonmanaXCost(alt_costs.AltCost):
    nonmana_x: bool = True


def parse(text: str) -> NonmanaXCost | None:
    match = re.fullmatch(r'exile a (?P<color>white|blue|black|red|green) card with mana value X from your hand', text)
    if match is None:
        return None
    selector = costs._selector(match['color'] + ' card with mana value X', zone='hand')
    if selector is None:
        return None
    component = costs.CostComponent(alt_costs.EXILE_FROM_HAND, amount=1, selector=selector, text=text)
    return NonmanaXCost('', costs.AbilityCost(components=(component,)))
