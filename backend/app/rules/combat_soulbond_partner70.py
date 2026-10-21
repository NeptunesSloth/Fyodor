"""Declaration permission requires a current paired object with soulbond (702.95)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.characteristics import AbilityText, Characteristics
    from app.rules.plan import Plan

TEXT = "This creature can't attack or block unless it's paired with a creature with soulbond."
CONDITION = 'paired_with_soulbond70'


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.kind != 'static' or ability.text != TEXT:
        return None
    from app.rules import statics

    return statics._definition('self', None, [{'static': 'not', 'cond': {'static': CONDITION}}],
                               rules=['cant_attack', 'cant_block'])


def holds(plan: Plan, source: CardInstance) -> bool:
    from app.rules import pairing

    oid = pairing.partner_oid(plan, source)
    if oid is None:
        return False
    partner = next((c for c in plan.state.cards.values() if c.zone.endswith(':battlefield') and plan.oid(c) == oid), None)
    return partner is not None and partner.controller == source.controller and plan.in_game(partner) \
        and plan.ch(partner).is_creature and 'soulbond' in plan.ch(partner).keywords
