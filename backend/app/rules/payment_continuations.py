"""Persistent post-payment stages; callbacks are registered code, never saved callables."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

from pydantic import TypeAdapter

from app.rules import mana as M

if TYPE_CHECKING:
    from app.rules.plan import Plan

T = TypeVar('T')
_HANDLERS: dict[str, tuple[TypeAdapter[Any], Callable[..., None]]] = {}
_PAYMENT = TypeAdapter(M.Payment)
_ABILITY = TypeAdapter(M.ManaAbility)


def register(name: str, kind: type[T], handler: Callable[[Plan, T, M.Payment | None], None]) -> None:
    _HANDLERS[name] = TypeAdapter(kind), handler


def continuation(plan: Plan, name: str, payload: Any) -> dict[str, Any]:
    adapter, _ = _HANDLERS[name]
    data = adapter.validate_python(payload)
    return {'do': 'paid_stage', 'stage': name, 'payload': adapter.dump_python(data, mode='json'),
            'actor': plan.actor, 'reserved_life': plan.reserved_life}


def ability_data(ability: M.ManaAbility) -> Any:
    return _ABILITY.dump_python(ability, mode='json')


def ability_of(data: Any) -> M.ManaAbility:
    return _ABILITY.validate_python(data)


def payment_data(payment: M.Payment | None) -> Any:
    return _PAYMENT.dump_python(payment, mode='json') if payment is not None else None


def payment_of(data: Any) -> M.Payment | None:
    return _PAYMENT.validate_python(data) if data is not None else None


def finish(plan: Plan, then: dict[str, Any], payment: M.Payment | None) -> None:
    from app.rules import replace

    replace.run_then(plan, {**then, 'payment': payment_data(payment)})


def _resume(plan: Plan, then: dict[str, Any]) -> None:
    if plan.rules.winner is not None or then['actor'] not in plan.live():
        return
    adapter, handler = _HANDLERS[then['stage']]
    actor, reserved = plan.actor, plan.reserved_life
    saved_reserved = then.get('reserved_life', 0)
    same_context = actor == then['actor'] and reserved == saved_reserved
    plan.actor, plan.reserved_life = then['actor'], saved_reserved
    try:
        handler(plan, adapter.validate_python(then['payload']), payment_of(then.get('payment')))
    finally:
        plan.actor = actor
        if not same_context:
            plan.reserved_life = reserved


@dataclass
class ManaRiderFrame:
    source: dict[str, Any]
    source_object: str
    player: str
    riders: list[tuple[str, int]]
    then: dict[str, Any]
    actor: str
    reserved_life: int


_RIDER = TypeAdapter(ManaRiderFrame)


def riders(plan: Plan, frame: ManaRiderFrame) -> bool:
    """Return false only when the replacement continuation owns further work."""
    from app.game.state import CardInstance
    from app.rules import casting, mana_riders, replace

    card = plan.state.cards.get(frame.source['id']) or CardInstance.model_validate(frame.source)
    for i, (kind, n) in enumerate(frame.riders):
        if kind == 'draw':
            rest = ManaRiderFrame(frame.source, frame.source_object, frame.player, frame.riders[i + 1:], frame.then, frame.actor, frame.reserved_life)
            after = {'do': 'mana_riders', 'frame': _RIDER.dump_python(rest, mode='json')}
            if not replace.draw_cards(plan, [frame.player], n, then=after):
                return False
        elif kind == 'damage' and casting._player_protected(plan, card, frame.player):
            plan.note(f'Protection prevents the damage {card.name} would deal to {plan.name(frame.player)}')
        elif kind == 'damage':
            rest = ManaRiderFrame(frame.source, frame.source_object, frame.player, frame.riders[i + 1:], frame.then, frame.actor, frame.reserved_life)
            after = {'do': 'mana_riders', 'frame': _RIDER.dump_python(rest, mode='json')}
            if not casting.mana_ability_damage(plan, card, frame.player, n, then=after, source_object=frame.source_object):
                return False
        else:
            mana_riders.after(plan, card, kind, n, frame.player)
    return True


def _resume_riders(plan: Plan, then: dict[str, Any]) -> None:
    from app.rules import replace

    frame = _RIDER.validate_python(then['frame'])
    actor, reserved = plan.actor, plan.reserved_life
    same_context = actor == frame.actor and reserved == frame.reserved_life
    plan.actor, plan.reserved_life = frame.actor, frame.reserved_life
    try:
        if riders(plan, frame):
            replace.run_then(plan, frame.then)
    finally:
        plan.actor = actor
        if not same_context:
            plan.reserved_life = reserved


from app.rules import replace as _replace  # noqa: E402

_replace.THEN['paid_stage'] = _resume
_replace.THEN['mana_riders'] = _resume_riders


@dataclass
class PaidManaSource:
    source: dict[str, Any]
    object_id: str
    index: int
    ability: M.ManaAbility


@dataclass
class PaymentRiderFrame:
    player: str
    payment: M.Payment
    sources: list[PaidManaSource]
    then: dict[str, Any]


_SOURCES = TypeAdapter(PaymentRiderFrame)


def payment_riders(plan: Plan, frame: PaymentRiderFrame) -> bool:
    from app.game.rules_state import emit
    from app.game.state import CardInstance
    from app.rules import casting

    for i, source in enumerate(frame.sources):
        card = plan.state.cards.get(source.source['id']) or CardInstance.model_validate(source.source)
        made = frame.payment.made110d.get(card.id, ())  # (wave 110D: what it produced, 605.3b)
        emit(plan.state, 'mana_added', object_id=source.object_id, card=card.id, player=frame.player, amount=len(made),
             counter='tap' if source.ability.tap else None, mana_colors110i=[c for c in dict.fromkeys(made) if c in 'WUBRG'])
        rest = PaymentRiderFrame(frame.player, frame.payment, frame.sources[i + 1:], frame.then)
        after = {'do': 'payment_sources', 'frame': _SOURCES.dump_python(rest, mode='json')}
        if not casting.after_mana_ability(plan, card, source.index, source.ability, frame.player,
                                          source_object=source.object_id, then=after):
            return False
    return True


def _resume_sources(plan: Plan, then: dict[str, Any]) -> None:
    frame = _SOURCES.validate_python(then['frame'])
    if payment_riders(plan, frame):
        finish(plan, frame.then, frame.payment)


_replace.THEN['payment_sources'] = _resume_sources
