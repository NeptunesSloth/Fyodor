"""Self entry replacements conditioned on the entering object's actual cast payment."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

CLAUSE = "If ~ would enter and it wasn't cast or no mana was spent to cast it, exile it instead."


def definition(text: str) -> dict[str, Any] | None:
    if text != CLAUSE:
        return None
    return {'kind': 'replacement', 'replacement': 'enters_exile_unpaid', 'effects': []}


def applies(plan: Plan, card: CardInstance, definitions: list[dict[str, Any]]) -> bool:
    if not any(d.get('replacement') == 'enters_exile_unpaid' for d in definitions):
        return False
    record = plan.rules.payments.get(plan.oid(card)) if card.id in plan.state.zones.get('stack', []) else None
    if record is not None and not record.mana_known:
        plan.note('The mana paid for this manually cast spell is unknown; apply its conditional entry replacement by hand.', [card.id])
        return False
    return record is None or record.cast_from is None or sum(record.mana_spent.values()) == 0


def divert(plan: Plan, card_id: str, actor: str) -> None:
    card = plan.state.cards[card_id]
    plan.do({'type': 'move', 'card_ids': [card_id], 'to': {'player': card.owner, 'zone': 'exile'}}, actor=actor)
