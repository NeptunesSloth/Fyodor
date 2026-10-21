"""Staged mandatory-if-able return costs; optional native payments own the commit."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption, ObjectRef

if TYPE_CHECKING:
    from app.rules.costs import AbilityCost
    from app.rules.plan import Plan

STEP = 'mandatory_return_payment43'
CLEAR = 'mandatory_return_clear43'
COST = "Return a creature you control to its owner's hand"


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = body.strip()
    text = text[:1].upper() + text[1:]
    if text != ("Return another creature you control to its owner's hand. If you do, put a +1/+1 counter on ~. "
                "Otherwise, you may return ~ to its owner's hand."):
        return None
    binding = '_mandatory_return43'
    return ([{'do': STEP, 'bind': binding}, {'do': CLEAR, 'bind': binding},
             {'do': 'only_if', 'cond': {'succeeded': binding}, 'skip': 1},
             {'do': 'add_counters', 'who': 'self', 'kind': '+1/+1', 'n': 1},
             {'do': 'only_if', 'cond': {'not': {'succeeded': binding}}, 'skip': 1},
             {'do': 'optional_payment', 'who': 'you', 'cost': "Return ~ to its owner's hand", 'bind': '_elder_self43'}], None, False)


def _cost() -> AbilityCost:
    from app.rules import optional_payment

    cost = optional_payment.parse(COST)
    assert cost is not None
    return cost


def start(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, cost_payment, costs, effects, optional_payment
    from app.rules.plan import decide

    binding = e['bind']
    previous = list(ctx.get('resolution_cost_exclusions') or [])
    ctx.setdefault('_mandatory_return_exclusions43', {})[binding] = previous
    # "Another" excludes the original source object. A new incarnation of the
    # same physical card is another object and can pay (CR400.7).
    context.bind_objects(plan, ctx, binding + '_source', effects._cards(plan, ctx, 'self'))
    ctx['resolution_cost_exclusions'] = [*previous, {'payer': ctx['controller'], 'who': 'ref:' + binding + '_source'}]
    cost = _cost()
    if optional_payment.problem(plan, ctx, cost, ctx['controller']) is not None:
        context.bind_payment(ctx, binding, False)
        return True
    source = optional_payment._source(plan, ctx)
    index, comp = next((i, c) for i, c in enumerate(cost.components) if c.kind == costs.RETURN_PERMANENT)
    was, plan.resolution_cost = plan.resolution_cost, True
    excluded = plan.excluded
    plan.excluded |= optional_payment._taken(plan, ctx, ctx['controller'])
    try:
        available = cost_payment.candidates(plan, comp, ctx['controller'], source)
    finally:
        plan.resolution_cost, plan.excluded = was, excluded
    refs = [ref for cid in available if (ref := context.ref_of(plan, cid)) is not None]
    if not refs:
        context.bind_payment(ctx, binding, False)
        return True
    opt = {'cost': COST, 'bind': binding, 'payer': ctx['controller'], 'chosen': {}}
    if len(refs) == 1:
        opt['chosen'] = {str(index): [refs[0].card]}
        optional_payment._pay(plan, ctx, opt, cost)
        return False  # the native payment continuation owns the remaining effects
    decide(plan, player=ctx['controller'], kind='choose_cards', prompt='Choose another creature to return to its owner’s hand',
           options=[DecisionOption(id=r.card, label=plan.state.cards[r.card].name or 'Creature', card_id=r.card) for r in refs],
           min_choices=1, max_choices=1,
           resume={'step': STEP, 'ctx': ctx, 'opt': opt, 'index': index, 'objects': [r.model_dump(mode='json') for r in refs]})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import context, effects, optional_payment

    if len(chosen) != 1 or chosen[0] not in {o.id for o in d.options}:
        raise ActionError('Choose one of the offered creatures')
    r = d.resume
    ref = next(ObjectRef.model_validate(raw) for raw in r['objects'] if raw['card'] == chosen[0])
    if context._same(plan, ref) is None:
        context.bind_payment(r['ctx'], r['opt']['bind'], False)
        effects.continue_effects(plan, r['ctx'])
        return
    opt = {**r['opt'], 'chosen': {str(r['index']): chosen}}
    optional_payment._pay(plan, r['ctx'], opt, _cost())


def clear(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    previous = ctx.get('_mandatory_return_exclusions43', {}).pop(e['bind'], [])
    ctx['resolution_cost_exclusions'] = previous
    return True


PRIMITIVES = {STEP: start, CLEAR: clear}
RESUME = {STEP: resume}
