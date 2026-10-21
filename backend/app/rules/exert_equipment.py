"""Reveal until Equipment and enter it attached to the exact exerted creature."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import ObjectRef
from app.game.state import zone_key
from app.rules import context

if TYPE_CHECKING:
    from app.rules.plan import Plan

_TEXT = ('Reveal cards from the top of your library until you reveal an Equipment card. Put that card onto the battlefield '
         'attached to that creature, then put the rest on the bottom of your library in a random order.')
_KEY = 'exert_equipment'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    if body.strip().casefold() == _TEXT.casefold():
        return [{'do': _KEY, 'who': 'event'}, {'do': _KEY + '_rest'}], None, False
    return None


def reveal(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import attachments, effects

    pid = ctx['controller']
    library = list(plan.state.zones.get(zone_key(pid, 'library'), [])) if pid in plan.live() else []
    found = next((i for i, cid in enumerate(library) if 'Equipment' in plan.ch(plan.state.cards[cid]).subtypes), None)
    top = library if found is None else library[:found + 1]
    ctx[_KEY] = [ref.model_dump(mode='json') for cid in top if (ref := context.ref_of(plan, cid)) is not None]
    if not top:
        return True
    for at in range(0, len(top), 250):
        plan.do({'type': 'reveal', 'card_ids': top[at:at + 250]}, actor=pid)
    if found is None:
        return True
    hosts = effects._cards(plan, ctx, 'event')
    entry: dict[str, Any] = {'card': top[-1], 'player': pid, 'actor': pid}
    if hosts:
        entry['host'] = hosts[0]
    return attachments.enter(plan, [entry], ctx)


def rest(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    pid = ctx['controller']
    refs = ctx.pop(_KEY, [])
    cards = [card.id for ref in refs if (card := context._same(plan, ObjectRef.model_validate(ref))) is not None
             and card.zone == zone_key(pid, 'library')]
    if cards and pid in plan.live():
        effects.bottom_at_random(plan, pid, cards)
    return True


PRIMITIVES = {_KEY: reveal, _KEY + '_rest': rest}
