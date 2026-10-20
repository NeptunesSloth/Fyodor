"""Native Madness alternatives with a fixed life component (702.35,118.9)."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

_PATTERN = re.compile(r'^madness(?: |—)(?P<cost>(?:\{[^}]+\})+(?:, Pay \d+ life)?)$', re.IGNORECASE)


def line(text: str) -> str | None:
    from app.rules.effect_cast_costs import textual_alternative

    match = _PATTERN.fullmatch(text.strip().rstrip('.'))
    if match is None:
        return None
    text = match['cost']
    textual_alternative(text)
    return text


def problem(plan: Plan, card: CardInstance, text: str) -> str | None:
    from app.rules import alt_costs, casting, costs
    from app.rules.effect_cast_costs import textual_alternative

    _, nonmana = textual_alternative(text)
    ch = plan.ch(card)
    full = alt_costs.merged(costs.spell_additional_cost(ch.abilities), nonmana)
    return casting.additional_problem(plan, full, card, card.owner) if full is not None else None
