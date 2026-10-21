"""Reveal a creature card sharing a controlled creature's type, then cast or bottom it."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import ObjectRef
from app.game.state import zone_key
from app.rules import context
from app.rules.creature_types import CREATURE_TYPES

if TYPE_CHECKING:
    from app.rules.plan import Plan

_TEXT = ("Reveal the top card of your library. If it's a creature card that shares a creature type with a creature "
         "you control, you may cast it without paying its mana cost. If you don't cast it, put it on the bottom of your library.")
_KEY = 'descendants_path'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    if body.strip().casefold() == _TEXT.casefold():
        return [{'do': _KEY}, {'do': _KEY + '_bottom'}], None, False
    return None


def begin(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import granted_casts

    ctx.pop(_KEY, None)
    pid = ctx['controller']
    library = plan.state.zones.get(zone_key(pid, 'library'), [])
    if pid not in plan.live() or not library:
        return True
    cid = library[0]
    ref = context.ref_of(plan, cid)
    if ref is None:
        return True
    ctx[_KEY] = ref.model_dump(mode='json')
    plan.do({'type': 'reveal', 'card_ids': [cid]}, actor=pid)
    ch = plan.ch(plan.state.cards[cid])
    if not ch.is_creature or not any(
            card.controller == pid and card.zone.endswith(':battlefield') and plan.in_game(card)
            and (held := plan.ch(card)).is_creature and bool(ch.subtypes & held.subtypes & CREATURE_TYPES)
            for card in plan.state.cards.values()):
        return True
    # Eligibility concerns the revealed card. The permission may cast any legal
    # face/adventure, including one whose spell is not itself a creature.
    return granted_casts.ask(plan, ctx, player=pid, cid=cid, head='A creature sharing a creature type',
                             no='Put it on the bottom', decline='ripple')


def bottom(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    saved = ctx.pop(_KEY, None)
    if saved is None:
        return True
    card = context._same(plan, ObjectRef.model_validate(saved))
    pid = ctx['controller']
    if card is not None and pid in plan.live() and card.zone == zone_key(pid, 'library'):
        plan.do({'type': 'move', 'card_ids': [card.id], 'to': {'player': pid, 'zone': 'library'}, 'position': 'bottom'}, actor=pid)
    return True


PRIMITIVES = {_KEY: begin, _KEY + '_bottom': bottom}
