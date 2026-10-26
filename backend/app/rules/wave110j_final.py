"""Wave 110J final pass: effect primitives of the last unsettled-then-settled cards (each block names its rule)."""

from __future__ import annotations

from typing import Any

from app.game.rules_state import emit
from app.rules import effects
from app.rules.plan import Plan


def mentored(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """702.134c: the mentor ability resolved (its target was still legal, 608.2b), so the source creature "mentors" that creature."""
    for cid in effects._cards(plan, ctx, "target"):
        card = plan.state.cards.get(cid)
        if card is not None:
            emit(plan.state, "mentored", object_id=plan.oid(card), card=cid, player=ctx["controller"], source=ctx.get("source_object"),
                 by_card=ctx.get("source_card"))
    return True


PRIMITIVES = {"mentored110j": mentored}
