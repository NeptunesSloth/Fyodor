"""CR 701.64 and 702.186: object designation and conditional Infinity grants."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_WORDING = re.compile(r'^harness (?:~|this permanent|this artifact)$')


def definition(m: re.Match[str]) -> tuple[list[dict[str, Any]], None]:
    return [{'do': 'harness'}], None


def harness(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    card = plan.state.cards.get(ctx.get('source_card') or '')
    if (card is not None and card.zone.endswith(':battlefield') and plan.in_game(card)
            and plan.oid(card) == ctx.get('source_object') and card.choices.get('Harnessed') != 'Yes'):
        plan.do({'type': 'set_choice', 'card_id': card.id, 'key': 'Harnessed', 'value': 'Yes'}, actor=ctx['controller'])
        plan.note(f'{card.name} becomes harnessed', [card.id], actor=ctx['controller'])
    return True


def infinity(text: str) -> dict[str, Any] | None:
    """Infinity is a static self grant, rather than a conditional triggered ability."""
    from app.rules import granted, statics

    if not text.startswith('∞ — '):
        return None
    ability = granted.quote(text[len('∞ — '):])
    if ability is None or '"' in ability:
        return None
    return statics.parse(f'As long as ~ is harnessed, ~ has "{ability}".')


TEMPLATES = [(_WORDING, definition)]
PRIMITIVES = {'harness': harness}
