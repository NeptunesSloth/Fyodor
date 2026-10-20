"""CR 603.4, 608.2h: a source attacking a player with the greatest life total."""
from __future__ import annotations

from typing import Any

from app.rules.plan import Plan


def parse(text: str) -> dict[str, Any] | None:
    if text in ("it's attacking the player with the most life or tied for most life",
                "~ is attacking the player with the most life or tied for most life"):
        return {"source_attacking_most_life": True}
    return None


def holds(plan: Plan, ctx: dict[str, Any]) -> bool:
    """Use current combat state for the same object, otherwise its last known state.

    A creature removed from combat on the battlefield no longer qualifies (506.4).
    A departed source uses its own old object identity, even if that card returns (400.7).
    """
    card = plan.state.cards.get(ctx.get("source_card") or "")
    if card is not None and card.zone.endswith(":battlefield") and plan.oid(card) == ctx.get("source_object"):
        target = f"{card.attacking.kind}:{card.attacking.id}" if card.attacking is not None else None
    else:
        snap = plan.rules.lki.get(ctx.get("source_object") or "")
        target = snap.attack_on if snap is not None else None
    if target is None or not target.startswith("player:"):
        return False
    player = target.removeprefix("player:")
    live = plan.live()
    return player in live and all(plan.state.players[player].life >= plan.state.players[p].life for p in live)
