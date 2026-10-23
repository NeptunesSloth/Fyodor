"""Global morph cost increases, including originally nonmana morph costs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.game.rules_state import PaymentRecord
from app.game.state import CardInstance
from app.rules import costs as C
from app.rules import mana as M
from app.rules import payment_continuations as pc
from app.rules.characteristics import Characteristics
from app.rules.plan import Plan


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    if ability.text == 'All morph costs cost {2} more.':
        return {'kind': 'static', 'static': 'morph_tax78', 'amount': 2, 'effects': []}
    return None


def tax(state: Any, info: Any) -> int:
    from app.rules import permissions

    return sum(int(d['amount']) for _, _, d in permissions._table_statics(state, info, {'morph_tax78'}))


@dataclass
class NonmanaMorph:
    source: CardInstance
    object_id: str
    ch: Characteristics
    cost: C.AbilityCost
    objects: dict[int, list[str]]
    objects_oids: dict[str, str]
    kind: str
    text: str


def pay_nonmana(plan: Plan, action: Any, card: CardInstance, ch: Characteristics, text: str, kind: str, amount: int) -> None:
    from app.game.errors import ActionError
    from app.rules import casting, cost_payment, life_lock

    cost = casting.nonmana_cost(text)
    if cost is None:
        raise ActionError("That morph cost can't be paid here: turn it face up with the table tools")
    if (why := cost_payment.problem(plan, cost, card, plan.actor)) is not None:
        raise ActionError(why)
    if plan.state.players[plan.actor].life < cost.life:
        raise ActionError(f"You don't have {cost.life} life to pay")
    if (why := life_lock.pay_problem(plan.state, plan.info, plan.actor, cost.life)) is not None:
        raise ActionError(why)
    plan.reserved_life = cost.life
    chosen = cost_payment.choose(plan, action, cost, card, f'Turn {ch.name} face up')
    if chosen is None:
        return
    mana = M.parse_cost('{'+str(amount)+'}')
    purpose = casting.Purpose(special='turn_up', payment_method='morph')
    own_pool = casting.payment_mode(plan, plan.actor) == 'self'
    if own_pool and not casting.pool_covers(plan.state, plan.actor, mana, purpose, plan.info):
        raise ActionError(f"Tap your mana first: {mana.text()} isn't in your mana pool")
    frame = NonmanaMorph(card.model_copy(deep=True), plan.oid(card), ch, cost, chosen,
                         {cid: plan.oid(plan.state.cards[cid]) for ids in chosen.values() for cid in ids}, kind, text)
    casting.pay_then(plan, plan.actor, mana, f'paid {mana.text()} to turn {ch.name} face up',
                     then=pc.continuation(plan, 'morph_nonmana78', frame), sources=[] if own_pool else action.sources,
                     exclude=tuple(dict.fromkeys((card.id, *cost_payment.excluded(cost, card, chosen)))), purpose=purpose)


def _paid(plan: Plan, frame: NonmanaMorph, payment: M.Payment | None) -> None:
    from app.game.errors import ActionError
    from app.rules import casting, cost_payment, replace

    card = plan.state.cards.get(frame.source.id)
    if card is None or plan.oid(card) != frame.object_id or not card.face_down or not card.zone.endswith(':battlefield') or card.controller != plan.actor:
        raise ActionError('The original face-down permanent is no longer available')
    for i, ids in frame.objects.items():
        legal = cost_payment.candidates(plan, frame.cost.components[i], plan.actor, card)
        if any(cid not in legal or cid not in plan.state.cards or plan.oid(plan.state.cards[cid]) != frame.objects_oids[cid] for cid in ids):
            raise ActionError('The selected morph cost objects are no longer available')
    if plan.state.players[plan.actor].life < frame.cost.life:
        raise ActionError("You no longer have enough life to pay the morph cost")
    if frame.cost.life:
        replace.lose_life(plan, [(plan.actor, frame.cost.life)])
    cost_payment.pay(plan, frame.cost, card, frame.objects,
                     PaymentRecord(card=card.id, controller=plan.actor, total_cost=frame.text))
    for i, comp in enumerate(frame.cost.components):
        if comp.kind == 'REVEAL_FROM_HAND' and frame.objects.get(i):
            plan.do({'type': 'reveal', 'card_ids': frame.objects[i]}, actor=plan.actor)
            plan.do({'type': 'hide', 'card_ids': frame.objects[i]}, actor=plan.actor)
    plan.reserved_life = 0
    plan.do({'type': 'face_down', 'card_ids': [card.id], 'face_down': False})
    casting.turned_up(plan, card)
    plan.rules.passed = []
    if frame.kind == 'megamorph':
        replace.put_counters(plan, [(card.id, '+1/+1', 1)], by=plan.actor, then={'do': 'face_up_done'})


pc.register('morph_nonmana78', NonmanaMorph, _paid)
