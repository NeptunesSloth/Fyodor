"""CR 118.12, 701.21: an entering permanent's controller may tap it."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption
from app.rules import context
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'optional_event_tap'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    body = body.strip()
    if body[:1].upper() + body[1:] != ("They may tap that permanent. If they don't, you create a 1/1 white Vampire creature token with lifelink."):
        return None
    token = scripts._parse_effects_plain('Create a 1/1 white Vampire creature token with lifelink.')
    if token is None or token[1] is not None:
        return None
    return ([{'do': STEP, 'bind': 'entry_tapped'},
             {'do': 'only_if', 'cond': {'succeeded': 'entry_tapped', 'negate': True}, 'skip': len(token[0])},
             *token[0]], None, False)


def _permanent(plan: Plan, ctx: dict[str, Any]) -> str | None:
    found = context.objects(plan, ctx, context.EVENT)
    return next((cid for cid in found if plan.state.cards[cid].zone.endswith(':battlefield')
                 and not plan.state.cards[cid].tapped), None)


def start(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    players = context.players(plan, ctx, context.EVENT)
    cid = _permanent(plan, ctx)
    if cid is None or not players:
        context.bind_payment(ctx, e['bind'], False)
        return True
    decide(plan, player=players[0], kind='choose_one', prompt=f"{ctx.get('name') or 'The ability'}: tap this permanent?",
           options=[DecisionOption(id='tap', label='Tap it', card_id=cid), DecisionOption(id='decline', label="Don't tap it")],
           resume={'step': STEP, 'ctx': ctx, 'bind': e['bind']})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    if len(chosen) != 1 or chosen[0] not in {'tap', 'decline'}:
        raise ActionError('Choose whether to tap the entering permanent')
    ctx = d.resume['ctx']
    cid = _permanent(plan, ctx)
    paid = chosen[0] == 'tap' and cid is not None
    if paid:
        plan.do({'type': 'tap', 'card_ids': [cid], 'tapped': True, 'cost': True}, actor=d.player)  # ("you may tap … If you do": refused, not skipped)
    context.bind_payment(ctx, d.resume['bind'], paid)
    effects.continue_effects(plan, ctx)


PRIMITIVES = {STEP: start}
