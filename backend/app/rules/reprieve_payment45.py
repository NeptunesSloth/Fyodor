"""Magistrate consumer of original death and native payment receipts."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption, ObjectRef

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'reprieve_payment45'
BIND = '_reprieve_return45'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = body.strip()
    text = text[:1].upper() + text[1:]
    if text != ("You may remove that many reprieve counters from ~. If you do, return that card "
                "to the battlefield under its owner's control."):
        return None
    return ([{'do': STEP}], None, False)


def start(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context

    original = context.info(plan, ctx, 'event')
    new = (ctx.get('event') or {}).get('new_objects') or []
    if original is None or not new:
        from app.rules.plan import decide

        decide(plan, player=ctx['controller'], kind='manual_resolution',
               prompt='This save has no exact death receipt. Resolve the reprieve payment and return manually.',
               options=[DecisionOption(id='done', label='Done')], resume={'step': STEP, 'ctx': ctx})
        return False
    amount = int(original[1].mana_value)
    if amount < 1:
        return True
    refs = [ObjectRef.model_validate(raw) for raw in new]
    context.refs(ctx)[BIND] = {'kind': 'objects', 'objects': [r.model_dump(mode='json') for r in refs
                                                         if r.zone and r.zone.endswith(':graveyard')]}
    at = int(ctx['next'])
    # A vanished nontarget graveyard object does not stop offering the payment.
    # Explicit source removal does not acquire a YOU CONTROL restriction.
    ctx['effects'] = [*ctx['effects'][:at],
                      {'do': 'optional_payment', 'who': 'you', 'cost': f'Remove {amount} reprieve counters from ~',
                       'bind': BIND + '_paid'},
                      {'do': 'only_if', 'cond': {'succeeded': BIND + '_paid'}, 'skip': 1},
                      {'do': 'return_card', 'who': 'ref:' + BIND, 'to': 'battlefield', 'under': 'owner'},
                      *ctx['effects'][at:]]
    return True


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    if chosen != ['done']:
        raise ActionError('Finish the manual resolution')
    effects.continue_effects(plan, d.resume['ctx'])


PRIMITIVES = {STEP: start}
RESUME = {STEP: resume}
