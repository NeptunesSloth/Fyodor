"""CR 110.4, 608.2d/h: return another permanent sharing a type with an event object."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption
from app.rules import context
from app.rules.characteristics import PERMANENT_TYPES
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'shared_permanent_return'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    body = body.strip()
    if body[:1].upper() + body[1:] != ("You may return another permanent you control that shares a permanent type with it to its owner's hand."):
        return None
    return ([{'do': STEP, 'who': 'event'}], None, False)


def _options(plan: Plan, ctx: dict[str, Any]) -> list[str]:
    types = {t for _, ch in context.infos(plan, ctx, context.EVENT) for t in ch.types} & PERMANENT_TYPES
    event_oids = {r['object_id'] for r in (ctx.get('event') or {}).get('objects') or []}
    return [c.id for c in plan.state.cards.values() if c.zone.endswith(':battlefield') and plan.in_game(c)
            and c.controller == ctx['controller'] and plan.oid(c) not in event_oids and bool(plan.ch(c).types & types)]


def start(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    options = _options(plan, ctx)
    if not options:
        return True
    refs = [r.model_dump(mode='json') for cid in options if (r := context.ref_of(plan, cid)) is not None]
    decide(plan, player=ctx['controller'], kind='choose_cards',
           prompt=f"{ctx.get('name') or 'The ability'}: return another permanent sharing a permanent type?",
           options=[DecisionOption(id=cid, label=plan.ch(plan.state.cards[cid]).name or 'Permanent', card_id=cid) for cid in options],
           min_choices=0, max_choices=1, resume={'step': STEP, 'ctx': ctx, 'refs': refs})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    if len(chosen) > 1 or any(cid not in {r['card'] for r in d.resume['refs']} for cid in chosen):
        raise ActionError('Choose at most one of the eligible permanents')
    ctx = d.resume['ctx']
    still_eligible = set(_options(plan, ctx))
    context.refs(ctx)['shared_return'] = {'kind': 'objects', 'objects': [r for r in d.resume['refs']
                                                                      if r['card'] in chosen and r['card'] in still_eligible]}
    effects.bounce(plan, ctx, {'do': 'bounce', 'who': 'ref:shared_return'})
    effects.continue_effects(plan, ctx)


PRIMITIVES = {STEP: start}
