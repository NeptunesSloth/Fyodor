"""CR 701.57c, 400.7h, 608.2h: information about the discovered card after discovering."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.rules import context

if TYPE_CHECKING:
    from app.rules.plan import Plan


def parse(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    from app.rules import token_grammar

    m = re.fullmatch(r"Discover (?P<n>\d+)\. If the discovered card's mana value is less than (?P=n), "
                     r'create a number of tapped Treasure tokens equal to the difference\.', body)
    if m is None:
        return None
    created = token_grammar.parse('create a tapped Treasure token')
    if not created or len(created) != 1:
        return None
    return ([{'do': 'discover', 'n': int(m['n']), 'as': 'discovered', 'continue_resolution': True},
             {'do': 'measure_discovered_difference', 'who': 'ref:discovered', 'limit': int(m['n']), 'as': 'discovered_difference'},
             {**created[0], 'n': {'ref_amount': 'discovered_difference'}}], None, False)


def measure(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules.stack_interaction import mana_value

    binding = context.refs(ctx).get(e['who'][len(context.PREFIX):]) or {}
    objects = binding.get('objects') or []
    difference = 0
    if objects:
        original = objects[0]
        card = plan.state.cards.get(original['card'])
        mv = binding.get('discovered_mv')
        if card is not None and card.zone == 'stack':
            # 400.7h lets the rest of the effect find the spell that was cast: its chosen face/half.
            mv = mana_value(card, plan.ch(card))
        # In a hidden hand use the last public information, captured while exiled (608.2h).
        if mv is not None:
            difference = max(0, e['limit'] - int(mv))
    context.bind_amount(ctx, e['as'], difference)
    return True


PRIMITIVES = {'measure_discovered_difference': measure}
