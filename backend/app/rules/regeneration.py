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
    oid = plan.oid(card)  # (-- can't regenerate (wave 19E) -- 701.19c: a shield isn't applied to an object that can't be regenerated)
    return plan.rules.regen_shields.get(oid, 0) > 0 and oid not in plan.rules.no_regen


def regenerate(plan: Plan, card: CardInstance, *, consume: bool = True, shield_id: str | None = None) -> None:
    """Regenerate now, consuming a shield unless an immediate replacement supplies regeneration."""
    from app.rules import regeneration_riders

    oid = plan.oid(card)
    rider = next((s for s in regeneration_riders.shields(plan, oid) if s.id == shield_id), None)
    left = plan.rules.regen_shields.get(oid, 0)
    if consume and rider is not None:
        plan.rules.regeneration_riders.remove(rider)
    if consume:
        left -= 1
        if left > 0:
            plan.rules.regen_shields[oid] = left
        else:
            plan.rules.regen_shields.pop(oid, None)
    plan.note(f"{card.name} regenerates", [card.id], actor=card.controller)
    # -- turn state (wave 100H) -- "for each time it regenerated this turn" (701.19a)
    from app.game.rules_state import TurnFact, turn_log_now

    if (log100h := turn_log_now(plan.state)) is not None:
        log100h.facts.append(TurnFact(kind="regenerated", player=card.controller, object_id=oid))
    if consume and left <= 0:
        for marker in [m for m in card.effects if m.name == "Regeneration shield"]:
            plan.do({"type": "remove_effect", "card_ids": [card.id], "effect_id": marker.id}, actor=card.controller)
    if not card.tapped:
        plan.do({"type": "tap", "card_ids": [card.id], "tapped": True}, actor=card.controller)
    if card.is_attacking:
        plan.do({"type": "attack", "card_ids": [card.id], "target": None}, actor=card.controller)
    if card.is_blocking:
        plan.do({"type": "block", "card_id": card.id, "attacker_id": None}, actor=card.controller)
    if card.damage:
        plan.do({"type": "set_damage", "card_ids": [card.id], "value": 0}, actor=card.controller)
    plan.rules.deathtouched = [c for c in plan.rules.deathtouched if c != card.id]
    if card.id in plan.rules.blocked:
        plan.rules.blocked = [c for c in plan.rules.blocked if c != card.id]
    if consume and rider is not None:
        regeneration_riders.apply(plan, rider)


def umbra_armor(plan: Plan, card: CardInstance) -> CardInstance | None:
    """-- keywords (wave 15E) -- 702.89a: an Aura with umbra armor attached to the permanent (the oldest, when it has several:
    which replacement applies is its controller's choice, not asked here)."""
    for aura in plan.state.cards.values():
        if aura.attached_to == card.id and aura.zone.endswith(":battlefield") and not plan.manual(aura) and any(
                ab.kind == "keywords" and "umbra armor" in ab.keywords for ab in plan.ch(aura).abilities):
            return aura
    return None


def use_umbra_armor(plan: Plan, card: CardInstance, aura: CardInstance, actor: str | None) -> None:
    """702.89a: instead of being destroyed, remove all damage marked on the permanent and destroy the Aura."""
    plan.note(f"{card.name}: {aura.name}'s umbra armor is used instead", [card.id, aura.id], actor=actor)
    if card.damage:
        plan.do({"type": "set_damage", "card_ids": [card.id], "value": 0}, actor=actor)
    plan.rules.deathtouched = [c for c in plan.rules.deathtouched if c != card.id]
    if "indestructible" not in plan.ch(aura).keywords and not (shielded(plan, aura)):  # (the Aura is destroyed, 701.8)
        plan.do({"type": "move", "card_ids": [aura.id], "to": {"zone": "graveyard"}}, actor=actor)
    elif shielded(plan, aura):
        regenerate(plan, aura)


def survivors(plan: Plan, card_ids: list[str], *, can_regenerate: bool = True, actor: str | None = None) -> list[str]:
    """The cards that are really destroyed: shielded ones regenerate instead (unless they can't)."""
    # -- counters (wave 7C) -- 122.1c: a shield counter is removed instead
    from app.rules import regeneration_choices, shield_counters

    card_ids = regeneration_choices.protect(plan, card_ids, actor)
    card_ids = shield_counters.destroy_survivors(plan, card_ids, actor)
    kept = []
    for cid in card_ids:  # -- keywords (wave 15E) -- umbra armor: not regeneration, so "can't be regenerated" doesn't stop it
        armor = umbra_armor(plan, plan.state.cards[cid])
        if armor is not None and not (can_regenerate and shielded(plan, plan.state.cards[cid])):
            use_umbra_armor(plan, plan.state.cards[cid], armor, actor)
        else:
            kept.append(cid)
    card_ids = kept
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
