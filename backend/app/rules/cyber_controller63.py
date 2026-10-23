"""Bounded actual public mill cards returned with native face-down characteristics."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_BODY = "Each opponent mills X cards. Put all creature cards milled this way onto the battlefield face down under your control. They're 2/2 Cyberman artifact creatures."
_PUBLIC = ('graveyard', 'exile', 'battlefield', 'command', 'stack')


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    if body.strip().casefold() != _BODY.casefold():
        return None
    return [{'do': 'mill', 'who': 'each_opponent', 'n': {'x': 1}, 'as': 'cyber_mill63'},
            {'do': 'cyber_return63'}], None, False


def return_creatures(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects

    selected = [cid for cid in context.objects(plan, ctx, 'cyber_mill63')
                if plan.state.cards[cid].zone.rsplit(':', 1)[-1] in _PUBLIC
                and not plan.state.cards[cid].face_down and 'Creature' in plan.ch(plan.state.cards[cid]).types]
    context.bind_objects(plan, ctx, 'cyber_return63', selected)
    return effects.return_card(plan, ctx, {'do': 'return_card', 'who': 'ref:cyber_return63', 'to': 'battlefield',
                                          'under': 'you', 'face_down': True, 'spec': '2/2 Cyberman artifact creature'})


PRIMITIVES = {'cyber_return63': return_creatures}
