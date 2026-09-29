"""Regeneration (CR 701.19): a shield that replaces the next destruction of that permanent
this turn. Instead of being destroyed it is tapped, removed from combat and all damage marked
on it is removed. "Can't be regenerated" destruction ignores shields. Shields end at cleanup.
"""

from __future__ import annotations

from app.game.state import CardInstance
from app.rules.plan import Plan


def add_shield(plan: Plan, card_id: str) -> None:
    oid = plan.oid(card_id)
    plan.rules.regen_shields[oid] = plan.rules.regen_shields.get(oid, 0) + 1


def shielded(plan: Plan, card: CardInstance) -> bool:
    return plan.rules.regen_shields.get(plan.oid(card), 0) > 0


def regenerate(plan: Plan, card: CardInstance) -> None:
    """Use one shield on ``card`` (it must have one): tap, remove from combat, remove damage."""
    oid = plan.oid(card)
    left = plan.rules.regen_shields.get(oid, 0) - 1
    if left > 0:
        plan.rules.regen_shields[oid] = left
    else:
        plan.rules.regen_shields.pop(oid, None)
    plan.note(f"{card.name} regenerates", [card.id], actor=card.controller)
    if left <= 0:
        for marker in [m for m in card.effects if m.name == "Regeneration shield"]:
            plan.do({"type": "remove_effect", "card_ids": [card.id], "effect_id": marker.id}, actor=card.controller)
    if not card.tapped:
        plan.do({"type": "tap", "card_ids": [card.id], "tapped": True}, actor=card.controller)
    if card.attacking is not None:
        plan.do({"type": "attack", "card_ids": [card.id], "target": None}, actor=card.controller)
    if card.blocking:
        plan.do({"type": "block", "card_id": card.id, "attacker_id": None}, actor=card.controller)
    if card.damage:
        plan.do({"type": "set_damage", "card_ids": [card.id], "value": 0}, actor=card.controller)
    plan.rules.deathtouched = [c for c in plan.rules.deathtouched if c != card.id]
    if card.id in plan.rules.blocked:
        plan.rules.blocked = [c for c in plan.rules.blocked if c != card.id]


def survivors(plan: Plan, card_ids: list[str], *, can_regenerate: bool = True) -> list[str]:
    """The cards that are really destroyed: shielded ones regenerate instead (unless they can't)."""
    if not can_regenerate or not plan.rules.regen_shields:
        return card_ids
    out = []
    for cid in card_ids:
        card = plan.state.cards[cid]
        if shielded(plan, card):
            regenerate(plan, card)
        else:
            out.append(cid)
    return out
