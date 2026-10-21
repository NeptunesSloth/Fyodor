"""Destroy a permanent, then reveal into a permanent sharing its pre-destruction types."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_FORM = re.compile(
    r'(?P<destroy>Destroy target permanent an opponent controls)\. Its controller reveals cards from the top of their library '
    r'until they reveal a permanent card that shares a card type with that permanent\. They put that card onto the battlefield '
    r'and the rest on the bottom of their library in a random order\.')


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    m = _FORM.fullmatch(body.strip())
    if m is None:
        return None
    from app.rules import scripts

    native = scripts.parse_effects(m['destroy'] + '.')
    if native is None:
        return None
    return [{'do': 'destroy_type_reveal', 'destroy': native[0]}], native[1], False


def begin(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    cards = effects._cards(plan, ctx, 'target')
    if not cards:
        return True
    target = plan.state.cards[cards[0]]
    following = {'do': 'reveal_shared_permanent', 'player': target.controller, 'types': sorted(plan.ch(target).types)}
    at = int(ctx.get('next') or 0)
    ctx['effects'] = [*ctx['effects'][:at], *e['destroy'], following, *ctx['effects'][at:]]
    return True


def reveal(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    pid = e['player']
    if pid not in plan.live():
        return True
    library = list(plan.state.zones.get(f'{pid}:library', []))
    types = set(e['types'])
    found = next((c for c in library if (ch := plan.ch(plan.state.cards[c])).is_permanent_card and ch.types & types), None)
    looked = library[:library.index(found) + 1] if found is not None else library
    for at in range(0, len(looked), 250):
        plan.do({'type': 'reveal', 'card_ids': looked[at:at + 250]}, actor=pid)
    ctx['looked'], ctx['found'], ctx['looked_owner'] = looked, found, pid
    ctx.pop('looked_zone', None)
    at = int(ctx.get('next') or 0)
    ctx['effects'] = [*ctx['effects'][:at],
                      {'do': 'pick_looked', 'which': 'that', 'require_found': True, 'to': 'battlefield', 'by_owner': True},
                      {'do': 'rest_looked', 'to': 'bottom_random'},
                      *ctx['effects'][at:]]
    return True


PRIMITIVES = {'destroy_type_reveal': begin, 'reveal_shared_permanent': reveal}
