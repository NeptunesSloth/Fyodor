"""A linked pool becomes a resolved, exact-object play permission."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_TEMPORARY = re.compile(r'^until end of turn, you may play (?P<what>a card|cards you own) exiled with ~$')
_CHOICE = "choose a card exiled with ~. you may play that card this turn"


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = re.sub(r'\s+', ' ', body).strip().rstrip('.').lower()
    if (m := _TEMPORARY.fullmatch(text)) is not None:
        return [{'do': 'linked_play_pool', 'who': 'exiled_with', 'own': m['what'] == 'cards you own',
                 'limit': 1 if m['what'] == 'a card' else 0}], None, False
    if text == _CHOICE:
        return [{'do': 'return_choice', 'who': 'exiled_with', 'n': 1, 'upto': False, 'random': False,
                 'label': 'card', 'to': 'choose', 'as': 'linked_play_choice'},
                {'do': 'grant_play', 'who': 'ref:linked_play_choice', 'play': True, 'cast': True,
                 'until': 'end_of_turn', 'from_exile': True}], None, False
    return None


def grant_pool(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects, permissions

    cards = effects._cards(plan, ctx, 'exiled_with')
    if e.get('own'):
        cards = [c for c in cards if plan.state.cards[c].owner == ctx['controller']]
    context.bind_objects(plan, ctx, 'linked_play_pool', cards)
    return permissions.grant_play(plan, ctx, {'who': 'ref:linked_play_pool', 'play': True, 'cast': True,
                                             'until': 'end_of_turn', 'from_exile': True, 'limit': e.get('limit', 0)})


PRIMITIVES = {'linked_play_pool': grant_pool}
