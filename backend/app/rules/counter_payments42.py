"""Optional resolution counter payments with exact saved objects and atomic costs."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption, ObjectRef

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'counter_payment42'


class PaymentCounter(BaseModel):
    source: ObjectRef
    kind: str


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    forms = {
        'You may remove a counter from a creature or planeswalker you control. If you do, draw a card and create a 1/1 green and white Citizen creature token.': 'warden',
        'You may remove a +1/+1 counter from each of two creatures you control. If you do, draw a card and create a 2/2 colorless Robot artifact creature token.': 'dyadrine',
    }
    text = body.strip()
    text = text[:1].upper() + text[1:]
    if text not in forms:
        return None
    return ([{'do': STEP, 'mode': forms[text]}], None, False)


def pay(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, prohibitions
    from app.rules.plan import decide

    choices: list[dict[str, Any]] = []
    options = []
    for card in plan.state.cards.values():
        if not card.zone.endswith(':battlefield') or card.controller != ctx['controller'] or not plan.in_game(card):
            continue
        ch = plan.ch(card)
        if not ch.is_creature and not (e['mode'] == 'warden' and 'Planeswalker' in ch.types):
            continue
        for kind, n in card.counters.items():
            if n <= 0 or (e['mode'] == 'dyadrine' and kind != '+1/+1') or prohibitions.cant_remove_counters(plan, card.id, kind):
                continue
            ref = context.ref_of(plan, card.id)
            if ref is not None:
                options.append(DecisionOption(id=str(len(choices)), label=f'{card.name}: remove a {kind} counter', card_id=card.id))
                choices.append(PaymentCounter(source=ref, kind=kind).model_dump(mode='json'))
    need = 2 if e['mode'] == 'dyadrine' else 1
    if len(choices) < need:
        return True
    decide(plan, player=ctx['controller'], kind='choose_one', prompt='Remove counters to draw a card and create a token?',
           options=[DecisionOption(id='pay', label='Pay'), DecisionOption(id='decline', label='Decline')],
           resume={'step': STEP, 'ctx': ctx, 'e': e, 'choices': choices, 'options': [o.model_dump(mode='json') for o in options]})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import context, counter_removal_results, effects, prohibitions, scripts
    from app.rules.plan import decide

    r = d.resume
    ctx, e = r['ctx'], r['e']
    need = 2 if e['mode'] == 'dyadrine' else 1
    if not r.get('selecting'):
        if chosen == ['decline']:
            effects.continue_effects(plan, ctx)
            return
        if chosen != ['pay']:
            raise ActionError('Choose whether to pay')
        decide(plan, player=ctx['controller'], kind='choose_cards' if need == 2 else 'choose_one',
               prompt='Choose the counters to remove', options=[DecisionOption.model_validate(o) for o in r['options']],
               min_choices=need, max_choices=need, resume={**r, 'selecting': True})
        return
    if len(chosen) != need or len(set(chosen)) != need or any(not i.isdigit() or int(i) >= len(r['choices']) for i in chosen):
        raise ActionError('Choose the required distinct counter sources')
    selected = [PaymentCounter.model_validate(r['choices'][int(i)]) for i in chosen]
    if len({row.source.object_id for row in selected}) != need:
        raise ActionError('Choose distinct permanents')
    cards = [context._same(plan, row.source) for row in selected]
    if any(card is None or not card.zone.endswith(':battlefield') or card.controller != ctx['controller']
           or not (plan.ch(card).is_creature or (e['mode'] == 'warden' and 'Planeswalker' in plan.ch(card).types))
           or prohibitions.cant_remove_counters(plan, card.id, row.kind)
           or card.counters.get(row.kind, 0) < 1 for card, row in zip(cards, selected, strict=True)):
        effects.continue_effects(plan, ctx)
        return
    for card, row in zip(cards, selected, strict=True):
        assert card is not None
        if counter_removal_results.remove(plan, card.id, row.kind, 1, by=ctx['controller']) != 1:
            raise ActionError('The counter payment can no longer be paid')
    token = ('Draw a card. Create a 1/1 green and white Citizen creature token.' if e['mode'] == 'warden'
             else 'Draw a card. Create a 2/2 colorless Robot artifact creature token.')
    parsed = scripts.parse_effects(token)
    assert parsed is not None
    ctx['effects'][ctx['next']:ctx['next']] = parsed[0]
    effects.continue_effects(plan, ctx)


PRIMITIVES = {STEP: pay}
RESUME = {STEP: resume}
