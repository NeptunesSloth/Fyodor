"""Native Bloatfly prevention body with frozen actual-removal results."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'bloatfly_outcome44'


def definition(text: str) -> dict[str, Any] | None:
    if text.replace('this creature', '~') != (
        'If damage would be dealt to ~ while it has a +1/+1 counter on it, prevent that damage, '
        'remove that many +1/+1 counters from it, then give each player a rad counter for each '
        '+1/+1 counter removed this way.'
    ):
        return None
    return {'kind': 'static', 'static': 'replace', 'event': 'damage',
            'match': {'to': {'objects': {'self': True}}},
            'static_if': [{'static': 'self_counter', 'counter': '+1/+1', 'op': '>=', 'n': 1}],
            'op': {'do': 'prevent_all', 'prevention': True,
                   'rider': {'if': False, 'aggregation': 'recipient', 'effects': [{'do': STEP}]}},
            'effects': []}


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import counter_removal_results, effects

    source = plan.state.cards.get(ctx.get('source_card', ''))
    removed = 0
    if (source is not None and source.zone.endswith(':battlefield')
            and plan.rules.object_id(source.id) == ctx.get('source_object')):
        removed = counter_removal_results.remove(
            plan, source.id, '+1/+1', effects._amount(plan, ctx, {'ref_amount': 'that_damage'}),
            by=ctx['controller'])
    # Freeze the actual removal directly into the queued native instruction.
    # A saved counter replacement resumes that instruction, never this removal.
    at = ctx['next']
    ctx['effects'] = [*ctx['effects'][:at],
                      {'do': 'player_counter', 'who': 'each_player', 'counter': 'rad', 'n': removed},
                      *ctx['effects'][at:]]
    return True
