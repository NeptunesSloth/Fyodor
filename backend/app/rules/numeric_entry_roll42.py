"""Exact X-d6 stack-entry receipts before native counter replacement and SBA."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

WHAT = 'numeric_entry42_total'
_TEXT = ('As this creature enters, roll X d6. It enters with a number of +1/+1 counters '
         'on it equal to the total of those results.')


# -- Vedalken Squirrel-Whacker (wave 110E) -- 614.12a: two six-sided dice rolled as it enters; 208.4b / 613.4b: the first result is its base power, the second its base toughness
_TEXT2 = ('As this creature enters, roll a six-sided die twice. Its base power becomes the first result and its base toughness '
          'becomes the second result.')


def definition(text: str) -> dict[str, Any] | None:
    return {'kind': 'replacement', 'replacement': 'enters_numeric_roll', 'effects': []} if text in (_TEXT, _TEXT2) else None


class Receipt(BaseModel):
    version: Literal[1] = 1
    card: str
    object: str
    total: int
    count: int = Field(ge=0)
    dice: list[int] = Field(default_factory=list)  # (wave 110E) the results in the order rolled


def current_receipt(plan: Any, card: Any, answers: dict[str, str] | None) -> Receipt | None:
    answer = (answers or {}).get(WHAT)
    if answer is None:
        return None
    receipt = Receipt.model_validate_json(answer)
    return receipt if receipt.card == card.id and receipt.object == plan.oid(card) else None


def applies(plan: Any, card: Any, controller: str) -> bool:
    if plan.manual(card) or not plan.in_game(card):
        return False
    probe = card.model_copy(update={'zone': controller + ':battlefield', 'controller': controller})
    return any(a.text in (_TEXT, _TEXT2) for a in plan.ch(probe).abilities)


def run(plan: Any, card: Any, controller: str) -> bool:
    from app.rules import effects

    probe = card.model_copy(update={'zone': controller + ':battlefield', 'controller': controller})
    x = 2 if any(a.text == _TEXT2 for a in plan.ch(probe).abilities) else max(0, int((card.stack_info.x if card.stack_info is not None else 0) or 0))
    data = {'do': 'numeric_entry42', 'card': card.id, 'object': plan.oid(card)}
    ctx = {'controller': controller, 'source_card': card.id, 'source_object': plan.oid(card),
           'name': card.name, 'x': x, 'effects': [{'do': 'roll', 'sides': 6, 'count': x},
                                              {'do': 'numeric_entry42_record'}],
           'next': 0, 'body_done': data}
    return effects.run_body(plan, ctx)


def record(plan: Any, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    data = ctx['body_done']
    card = plan.state.cards.get(data['card'])
    if card is not None and card.zone == 'stack' and plan.oid(card) == data['object']:
        values = list(ctx.get('dice') or [])
        answer = Receipt(card=card.id, object=data['object'], total=sum(values), count=len(values), dice=values)
        plan.rules.entry_choices.setdefault(card.id, {})[WHAT] = answer.model_dump_json()
    return True


def resume(plan: Any, data: dict[str, Any]) -> None:
    from app.rules import engine

    card = plan.state.cards.get(data['card'])
    if (card is not None and card.zone == 'stack' and plan.oid(card) == data['object']
            and plan.state.zones.get('stack', [])[-1:] == [card.id]):
        engine.resolve_top_of_stack(plan)
    else:
        engine._after_resolution(plan)


def counter_total(plan: Any, card: Any, ch: Any, choices: dict[str, str] | None) -> int:
    answer = (choices or {}).get(WHAT)
    if not any(a.text == _TEXT for a in ch.abilities) or plan.manual(card) or answer is None:
        return 0
    receipt = Receipt.model_validate_json(answer)
    if receipt.card != card.id:
        return 0
    oid = plan.oid(card)
    same_entry = oid == receipt.object or any(
        e.kind == 'zone_change' and not e.manual and e.card == card.id and e.object_id == receipt.object
        and e.new_object_id == oid and e.from_zone == 'stack' and (e.to_zone or '').endswith(':battlefield')
        for e in plan.rules.events)
    return max(0, receipt.total) if same_entry else 0


def after_entry(plan: Any, card_id: str, choices: dict[str, str] | None) -> None:
    """The Squirrel-Whacker's dice are its base power and toughness from the moment it is on the battlefield (a layer 7b effect for this object)."""
    answer = (choices or {}).get(WHAT)
    card = plan.state.cards.get(card_id)
    if answer is None or card is None or not card.zone.endswith(':battlefield') or not any(a.text == _TEXT2 for a in plan.ch(card).abilities):
        return
    receipt = Receipt.model_validate_json(answer)
    if receipt.card == card.id and len(receipt.dice) == 2:
        from app.rules import layers

        layers.add_effect(plan, affected=[plan.oid(card)], layer='7b', source=plan.oid(card), controller=card.controller, power=receipt.dice[0],
                          toughness=receipt.dice[1], duration='permanent', label=f'{card.name}: base power and toughness from the dice')


PRIMITIVES = {'numeric_entry42_record': record}
THEN = {'numeric_entry42': resume}
