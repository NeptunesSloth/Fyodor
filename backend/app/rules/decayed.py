"""Decayed (702.147, wave 6C): "This creature can't block" and "When this creature attacks, sacrifice it at end of combat."

The static half is a block restriction (combat.block_problem reads the keyword, wherever it comes from). The triggered
half is a keyword trigger (scripts.keyword_triggers): as it resolves it creates a delayed triggered ability (603.7) that
triggers at the end of combat step (511.2) and sacrifices that object — only if it's still the same object on the
battlefield (400.7, 603.7c) and its controller is the delayed trigger's controller (701.21a: a player can sacrifice
only a permanent they control).
"""

from __future__ import annotations

import secrets
from typing import Any

from app.rules.plan import Plan

TRIGGER = {"kind": "triggered", "trigger": "attacks_self", "optional": False, "target": None,
           "effects": [{"do": "decayed_attacks"}]}


def decayed_attacks(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The attack trigger resolving: "sacrifice it at end of combat" (a delayed trigger, 603.7a)."""
    from app.game.rules_state import DelayedTrigger

    card, oid = ctx.get("source_card"), ctx.get("source_object")
    if not card or not oid:
        return True
    plan.rules.delayed.append(DelayedTrigger(
        id=secrets.token_hex(4), controller=ctx["controller"], source_card=card, source_object=oid,
        name=ctx.get("name") or "Decayed", when={"kind": "step", "step": "end_combat", "whose": "next"},
        effects=[{"do": "decayed_sacrifice", "card": card, "object": oid}],
        turn=plan.state.turn.number, step=plan.state.turn.phase))
    return True


def decayed_sacrifice(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    card = plan.state.cards.get(e["card"])
    if card is None or not card.zone.endswith(":battlefield") or plan.oid(card) != e["object"] \
            or card.controller != ctx["controller"]:
        return True
    effects._sacrifice_cards(plan, [card.id], card.controller, ctx)
    return True


PRIMITIVES = {"decayed_attacks": decayed_attacks, "decayed_sacrifice": decayed_sacrifice}
