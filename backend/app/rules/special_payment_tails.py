"""Saved terminal stages for special actions and abilities activated from the hand."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from app.game.mana_cost_templates import ForetellCostReceipt, GrantedManaCost
from app.game.rules_state import PaymentRecord, emit
from app.game.state import CardInstance
from app.rules import mana as M
from app.rules import payment_continuations as pc
from app.rules.characteristics import Characteristics
from app.rules.plan import Plan

if TYPE_CHECKING:
    from app.rules.casting import Purpose

Kind = Literal['transmute', 'cycling', 'suspend', 'plot', 'foretell', 'companion', 'face_up']


@dataclass
class SpecialPayment:
    kind: Kind
    card: CardInstance
    object_id: str
    ch: Characteristics
    ability_id: str | None = None
    effects: list[dict[str, Any]] = field(default_factory=list)
    number: int = 0
    faceup_kind: str | None = None
    original_cost: str | None = None
    total_cost: str = ""
    cost_has_x: bool | None = None
    granted_mana_cost: GrantedManaCost | None = None


def pay(plan: Plan, kind: Kind, card: CardInstance, ch: Characteristics, cost: M.ManaCost, label: str, *,
        sources: list[str] | None, purpose: Purpose, ability_id: str | None = None,
        effects: list[dict[str, Any]] | None = None, number: int = 0, faceup_kind: str | None = None,
        original_cost: str | None = None, granted_mana_cost: GrantedManaCost | None = None) -> None:
    from app.rules import casting

    frame = SpecialPayment(kind, card.model_copy(deep=True), plan.oid(card), ch, ability_id, effects or [], number, faceup_kind,
                           original_cost, cost.text(), "{X}" in original_cost if original_cost is not None else purpose.selected_cost_has_x, granted_mana_cost)
    casting.pay_then(plan, plan.actor, cost, label, sources=sources, purpose=purpose,
                     then=pc.continuation(plan, 'special_action', frame))


def _paid(plan: Plan, frame: SpecialPayment, payment: M.Payment | None) -> None:
    from app.rules import casting, replace

    card = plan.state.cards.get(frame.card.id) or frame.card
    kind, ch = frame.kind, frame.ch
    if kind in ('transmute', 'cycling'):
        if kind == 'cycling':
            casting._activated(plan, 'cycling')
            plan.cycling_card = card.id
        try:
            plan.do({'type': 'move', 'card_ids': [card.id], 'to': {'player': card.owner, 'zone': 'graveyard'}})
        finally:
            plan.cycling_card = None
        if kind == 'cycling':
            emit(plan.state, 'cycled', object_id=frame.object_id, card=card.id, player=plan.actor, amount=frame.number)
        if frame.ability_id is not None:
            record = PaymentRecord(card=frame.ability_id, controller=plan.actor, total_cost=frame.total_cost,
                                   mana_spent=dict(payment.spent) if payment is not None else {},
                                   mana_tags=payment.tags if payment is not None else [],
                                   mana_sources=payment.sources if payment is not None else [],
                                   life=payment.life if payment is not None else 0,
                                   activation_life_paid=max(0, payment.life-payment.auxiliary_life) if payment is not None else 0,
                                   activation_cost_has_x=frame.cost_has_x, activation_cost_has_tap=False, x=frame.number if frame.cost_has_x else None,
                                   discarded=[card.id], discarded_objects=[plan.oid(card)])
            casting.record_payment(plan, frame.ability_id, record)
        casting._stacked(plan, card, frame.object_id, ch, frame.ability_id, frame.effects, cost_has_x=frame.cost_has_x,
                         x=frame.number if frame.cost_has_x else None)
        return
    if kind == 'face_up':
        from app.rules import chosen_forms95

        if chosen_forms95.prepare_up(plan, card, actor=plan.actor, kind=frame.faceup_kind):
            return
        plan.do({'type': 'face_down', 'card_ids': [card.id], 'face_down': False})
        casting.turned_up(plan, card)
        plan.rules.passed = []
        if frame.faceup_kind == 'megamorph':
            replace.put_counters(plan, [(card.id, '+1/+1', 1)], by=plan.actor, then={'do': 'face_up_done'})
        return
    zone = 'foretell' if kind == 'foretell' else 'hand' if kind == 'companion' else 'exile'
    plan.do({'type': 'move', 'card_ids': [card.id], 'to': {'player': card.owner, 'zone': zone}})
    if kind == 'suspend':
        after = pc.continuation(plan, 'special_suspend_done', frame)
        if frame.number and not replace.put_counters(plan, [(card.id, 'time', frame.number)], by=plan.actor,
                                                      effect=False, then=after):
            return
        _suspended(plan, frame, None)
        return
    elif kind == 'plot':
        casting.become_plotted(plan, card.id)
    elif kind == 'foretell':
        plan.rules.foretold[card.id] = plan.state.turn.number
        if frame.granted_mana_cost is not None:
            plan.rules.foretell_templates[card.id] = ForetellCostReceipt(plan.oid(card), frame.granted_mana_cost)
        emit(plan.state, "foretold", object_id=plan.oid(card), card=card.id, player=plan.actor)
        plan.note(f'{plan.name(plan.actor)} foretells a card')
    elif kind == 'companion':
        plan.note(f'{plan.name(plan.actor)} puts their companion {ch.name} into their hand', [card.id])
    plan.rules.passed = []


def _suspended(plan: Plan, frame: SpecialPayment, payment: M.Payment | None) -> None:
    plan.rules.suspended.append(frame.card.id)
    plan.note(f"{frame.ch.name} is suspended with {frame.number} time counter{'s' if frame.number != 1 else ''}", [frame.card.id])
    plan.rules.passed = []


pc.register('special_action', SpecialPayment, _paid)

pc.register('special_suspend_done', SpecialPayment, _suspended)
