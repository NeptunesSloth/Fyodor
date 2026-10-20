"""Exact numeric activation costs with persistent finalized receipts."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict

from app.game.rules_state import NumericRollCostReceipt as Receipt

if TYPE_CHECKING:
    from app.rules.plan import Plan


_TEXT = '{6}, Roll a d8: Monstrosity X, where X is the result.'


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    return {'kind': 'activated', 'effects': [{'do': 'monstrosity', 'n': {'x': 1}}]} if ability.text == _TEXT else None


class Frame(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: Literal[1] = 1
    source: str
    source_object: str
    ability: str
    ability_object: str
    roller: str
    then: dict[str, Any]
    receipt: Receipt | None = None


def run(plan: Plan, frame: Frame) -> None:
    """Only a trusted already-committed caller may supply this continuation."""
    from app.rules import effects

    ctx: dict[str, Any] = {'controller': frame.roller, 'source_card': frame.source, 'source_object': frame.source_object,
           'effects': [{'do': 'roll', 'sides': 8, 'count': 1}, {'do': 'random_cost44_record'}], 'next': 0,
           'body_done': {'do': 'random_cost44_complete', 'frame': frame.model_dump()}}
    if effects.run_body(plan, ctx):
        complete(plan, ctx['body_done'])


def record(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    frame = Frame.model_validate(ctx['body_done']['frame'])
    # Existing native post-activation X is a trusted finalized receipt here,
    # not an announced client X and not a second resolution-time roll.
    frame.receipt = Receipt(source_object=frame.source_object, ability_object=frame.ability_object,
                            roller=frame.roller, results=list(ctx['dice']))
    frame.then['payload']['resolved_x'] = frame.receipt.result
    frame.then['payload']['numeric_roll_cost'] = frame.receipt.model_dump()
    ctx['body_done']['frame'] = frame.model_dump()
    return True


def complete(plan: Plan, data: dict[str, Any]) -> None:
    from app.rules import replace

    frame = Frame.model_validate(data['frame'])
    if frame.receipt is None or (frame.receipt.source_object, frame.receipt.ability_object, frame.receipt.roller) != (
            frame.source_object, frame.ability_object, frame.roller):
        raise ValueError('The finalized cost-roll receipt does not match its activation')
    card = plan.state.cards.get(frame.ability)
    if card is None or card.zone != 'stack' or plan.oid(card) != frame.ability_object:
        raise ValueError('The pending cost-roll activation no longer exists')
    replace.run_then(plan, frame.then)


PRIMITIVES = {'random_cost44_record': record}
THEN = {'random_cost44_complete': complete}
