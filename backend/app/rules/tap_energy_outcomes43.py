"""Actual tap recipients followed by native energy payment and counter choices."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption, ObjectRef

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'tap_energy43'
SELECT = 'tap_energy_select43'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = body.strip()
    text = text[:1].upper() + text[1:]
    if text != ('Tap all creatures target player controls. You may pay any amount of {E}. '
                'If you do, choose up to that many creatures tapped this way. Put a stun counter on each of them.'):
        return None
    from app.rules import scripts

    native = scripts.parse_effects('Tap all creatures target player controls.')
    assert native is not None and len(native[0]) == 1
    return ([{'do': STEP, 'tap': native[0][0], 'bind': '_tap_energy43'},
             {'do': SELECT, 'bind': '_tap_energy43'}], native[1], False)


def start(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects, group_choice
    from app.rules.plan import decide

    # This is the exact action payload committed by the native tap primitive;
    # no before/after table delta or already-tapped object is a receipt.
    tap = e['tap']
    ids = [cid for cid in effects._cards(plan, ctx, tap['who']) if not plan.state.cards[cid].tapped]
    effects.tap(plan, ctx, tap)
    context.bind_objects(plan, ctx, e['bind'] + '_tapped', ids)
    maximum = max(0, plan.state.players[ctx['controller']].resources.get('energy', 0))
    if not maximum:
        context.bind_amount(ctx, e['bind'] + '_amount', 0)
        return True
    decide(plan, player=ctx['controller'], kind='choose_one', prompt=f'Pay 0–{maximum} energy',
           options=[DecisionOption(id=group_choice.NUMBER, label='Type a number ≥ 0', group='number')],
           resume={'step': STEP, 'ctx': ctx, 'e': e, 'maximum': maximum})
    return False


def resume_amount(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import context, effects, optional_payment

    if len(chosen) != 1 or not chosen[0].isdigit() or not 0 <= int(chosen[0]) <= d.resume['maximum']:
        raise ActionError('Choose an amount of energy in the offered range')
    n = int(chosen[0])
    ctx, e = d.resume['ctx'], d.resume['e']
    context.bind_amount(ctx, e['bind'] + '_amount', n)
    if not n:
        effects.continue_effects(plan, ctx)
        return
    cost_text = f'Pay {n} {{E}}'
    cost = optional_payment.parse(cost_text)
    assert cost is not None
    if optional_payment.problem(plan, ctx, cost, ctx['controller']) is not None:
        raise ActionError('The energy payment can no longer be paid')
    optional_payment._pay(plan, ctx, {'cost': cost_text, 'bind': e['bind'], 'payer': ctx['controller'], 'chosen': {}}, cost)


def select(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects
    from app.rules.plan import decide

    n = effects._amount(plan, ctx, {'ref_amount': e['bind'] + '_amount'})
    if not n:
        return True
    refs = [ref for cid in effects._cards(plan, ctx, 'ref:' + e['bind'] + '_tapped')
            if plan.ch(plan.state.cards[cid]).is_creature and (ref := context.ref_of(plan, cid)) is not None]
    if not refs:
        return True
    decide(plan, player=ctx['controller'], kind='choose_cards', prompt='Choose creatures tapped this way to receive stun counters',
           options=[DecisionOption(id=r.card, label=plan.state.cards[r.card].name or 'Creature', card_id=r.card) for r in refs],
           min_choices=0, max_choices=min(n, len(refs)),
           resume={'step': SELECT, 'ctx': ctx, 'e': e, 'objects': [r.model_dump(mode='json') for r in refs]})
    return False


def resume_select(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import context, effects

    r = d.resume
    if len(set(chosen)) != len(chosen) or not set(chosen) <= {o.id for o in d.options} or len(chosen) > d.max_choices:
        raise ActionError('Choose up to the offered number of creatures')
    refs = [ObjectRef.model_validate(raw) for raw in r['objects'] if raw['card'] in chosen]
    cards = [c.id for ref in refs if (c := context._same(plan, ref)) is not None and plan.ch(c).is_creature]
    binding = r['e']['bind'] + '_selected'
    context.bind_objects(plan, r['ctx'], binding, cards)
    if cards:
        r['ctx']['effects'][r['ctx']['next']:r['ctx']['next']] = [
            {'do': 'add_counters', 'who': 'ref:' + binding, 'kind': 'stun', 'n': 1}]
    effects.continue_effects(plan, r['ctx'])


PRIMITIVES = {STEP: start, SELECT: select}
RESUME = {STEP: resume_amount, SELECT: resume_select}
