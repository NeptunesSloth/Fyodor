"""CR 118.12 / 107.3: choose X by selecting untapped permanents to pay a tap cost."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.rules.plan import Plan


def payment(phrase: str) -> dict[str, Any] | None:
    from app.rules import costs, optional_payment

    m = re.fullmatch(r'tap X (?P<what>untapped .+ you control)', phrase)
    if m is None:
        return None
    cost = optional_payment.parse('Tap 1 ' + m['what'])
    if cost is None or len(cost.components) != 1 or cost.components[0].kind != costs.TAP_OTHER:
        return None
    return {'cost': '', 'choose_x': {'max': None, 'tap_cost': m['what']}}


def start(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], payer: str, bind: str) -> bool:
    from app.rules import cost_payment, optional_payment, values

    phrase = e['choose_x']['tap_cost']
    cost = optional_payment.parse('Tap 1 ' + phrase)
    assert cost is not None
    source = optional_payment._source(plan, ctx)
    pool = cost_payment.candidates(plan, cost.components[0], payer, source)
    cap = e['choose_x'].get('max')
    most = min(len(pool), values.evaluate(plan, ctx, cap)) if cap is not None else len(pool)
    if most == 0:
        pool = []
    decide(plan, player=payer, kind='choose_cards',
           prompt=f"{ctx.get('name') or 'It'}: choose untapped permanents to tap (X is how many), or decline",
           options=[DecisionOption(id=cid, label=plan.state.cards[cid].name or 'Permanent', card_id=cid) for cid in pool]
                   + [DecisionOption(id=optional_payment.DECLINE, label="Don't pay")],
           min_choices=0, max_choices=max(1, most),
           resume={'step': optional_payment.STEP, 'ctx': ctx,
                   'choose_x': {'bind': bind, 'payer': payer, 'tap_cost': phrase, 'max_tap': most}, 'cost': ''})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects, optional_payment, paid_x

    ctx, info = d.resume['ctx'], d.resume['choose_x']
    bind, payer = info['bind'], info['payer']
    if len(set(chosen)) != len(chosen) or not set(chosen) <= {o.id for o in d.options}:
        raise ActionError('Choose only the offered untapped permanents')
    if optional_payment.DECLINE in chosen:
        if len(chosen) != 1:
            raise ActionError('Decline or choose permanents, not both')
        plan.note(f"{plan.name(payer)} didn't pay for {ctx.get('name') or 'it'}")
        paid_x._record(ctx, bind, False, 0)
    elif not chosen:
        plan.note(f"{plan.name(payer)} chooses X = 0 for {ctx.get('name') or 'it'}")
        paid_x._record(ctx, bind, True, 0)
    else:
        n = len(chosen)
        if n > info['max_tap']:
            raise ActionError('That many permanents exceeds the limit for X')
        text = f"Tap {n} {info['tap_cost']}"
        cost = optional_payment.parse(text)
        assert cost is not None
        selected = {0: chosen}
        if why := optional_payment.problem(plan, ctx, cost, payer, selected):
            raise ActionError(f"Can't pay {text}: {why}")
        ctx.setdefault('paid_x', {})[bind] = n
        optional_payment._pay(plan, ctx, {'cost': text, 'bind': bind, 'payer': payer, 'chosen': selected}, cost)
        return
    effects.continue_effects(plan, ctx)
