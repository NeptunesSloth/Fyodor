"""Exact latest-public-mill type-set continuation for Demonic Covenant."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_BODY = "Create a 5/5 black Demon creature token with flying, then mill two cards. If two cards that share all their card types were milled this way, sacrifice ~."
_PUBLIC = ('graveyard', 'exile', 'battlefield', 'command', 'stack')


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    if body.strip().casefold() != _BODY.casefold():
        return None
    token = scripts.parse_effects('Create a 5/5 black Demon creature token with flying.')
    if token is None or token[1] is not None or token[2]:
        return None
    return [*token[0], {'do': 'mill', 'who': 'you', 'n': 2, 'as': 'covenant_mill62'},
            {'do': 'covenant_types62'}], None, False


def matching_types(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects

    seen: set[frozenset[str]] = set()
    for cid in context.objects(plan, ctx, 'covenant_mill62'):
        card = plan.state.cards[cid]
        if card.zone.rsplit(':', 1)[-1] not in _PUBLIC or card.face_down:
            continue
        types = frozenset(plan.ch(card).types)
        if types in seen:
            return effects.sacrifice(plan, ctx, {'who': 'self'})
        seen.add(types)
    return True


PRIMITIVES = {'covenant_types62': matching_types}
