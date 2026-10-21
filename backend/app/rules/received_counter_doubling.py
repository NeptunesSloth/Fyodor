"""Double counters only on exact creatures that actually received the preceding put."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.rules import context

if TYPE_CHECKING:
    from app.rules.plan import Plan

_TEXT = re.compile(r'Put a \+1/\+1 counter on (?P<who>target|each) creature you control, then double the number of \+1/\+1 '
                   r'counters on each creature that had a \+1/\+1 counter put on it this way\.', re.I)


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    m = _TEXT.fullmatch(body.strip())
    if m is None:
        return None
    from app.rules import scripts

    first = scripts.parse_effects(f"Put a +1/+1 counter on {m['who'].lower()} creature you control.")
    if first is None or len(first[0]) != 1 or first[0][0]['do'] != 'add_counters':
        return None
    return ([{**first[0][0], 'did': 'received_put', 'reflex': True},
             {'do': 'double_received_counters', 'bind': 'received_put', 'kind': '+1/+1'}], first[1], False)


def double_received(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, replace

    probe = context.refs(ctx).get(e['bind']) or {}
    receivers = [cid for cid, (oid, before) in (probe.get('counters_up') or {}).items()
                 if (card := plan.state.cards.get(cid)) is not None and plan.oid(card) == oid
                 and card.zone.endswith(':battlefield') and plan.ch(card).is_creature
                 and card.counters.get(e['kind'], 0) > before]
    puts = [(cid, e['kind'], plan.state.cards[cid].counters[e['kind']]) for cid in receivers]
    if not puts:
        return True
    # Keep this primitive's continuation: a nested primitive's different effect
    # descriptor cannot pause for a second counter-replacement choice.
    return replace.put_counters(plan, puts, by=ctx['controller'], then=effects._then(ctx, e), ctx=ctx)


PRIMITIVES = {'double_received_counters': double_received}
