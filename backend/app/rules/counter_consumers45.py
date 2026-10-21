"""Exact mandatory resolution counter payment with saved original objects."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption
from app.rules.counter_payments42 import PaymentCounter

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'mandatory_counter_consumer45'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = body.strip()
    text = text[:1].upper() + text[1:]
    if text == 'Remove a counter from a creature you control. If you do, draw a card.':
        return ([{'do': STEP}], None, False)
    return None


def start(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, prohibitions
    from app.rules.plan import decide

    choices: list[dict[str, Any]] = []
    options = []
    for card in plan.state.cards.values():
        if (not card.zone.endswith(':battlefield') or card.controller != ctx['controller']
                or not plan.in_game(card) or not plan.ch(card).is_creature):
            continue
        ref = context.ref_of(plan, card.id)
        if ref is None:
            continue
        for kind, amount in card.counters.items():
            if amount <= 0 or prohibitions.cant_remove_counters(plan, card.id, kind):
                continue
            options.append(DecisionOption(id=str(len(choices)), label=f'{card.name}: remove a {kind} counter', card_id=card.id))
            choices.append(PaymentCounter(source=ref, kind=kind).model_dump(mode='json'))
    if not choices:
        return True
    decide(plan, player=ctx['controller'], kind='choose_one', prompt='Choose a counter to remove',
           options=options, min_choices=1, max_choices=1,
           resume={'step': STEP, 'ctx': ctx, 'choices': choices})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import context, counter_removal_results, effects, prohibitions

    raw = d.resume
    if len(chosen) != 1 or chosen[0] not in {o.id for o in d.options}:
        raise ActionError('Choose one counter to remove')
    selected = PaymentCounter.model_validate(raw['choices'][int(chosen[0])])
    card = context._same(plan, selected.source)
    ctx = raw['ctx']
    # Revalidate the saved incarnation, controller/type and actual payable kind.
    if (card is not None and card.zone.endswith(':battlefield') and plan.in_game(card)
            and card.controller == ctx['controller'] and plan.ch(card).is_creature
            and card.counters.get(selected.kind, 0) >= 1
            and not prohibitions.cant_remove_counters(plan, card.id, selected.kind)):
        actual = counter_removal_results.remove(plan, card.id, selected.kind, 1, by=ctx['controller'])
        if actual == 1:
            at = int(ctx['next'])
            ctx['effects'] = [*ctx['effects'][:at], {'do': 'draw', 'who': 'you', 'n': 1}, *ctx['effects'][at:]]
    effects.continue_effects(plan, ctx)


PRIMITIVES = {STEP: start}
RESUME = {STEP: resume}
