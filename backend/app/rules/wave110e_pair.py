"""-- wave 110E -- Bitter Feud: the pair test of "If a source controlled by one of the chosen players would deal damage to the other chosen player or a
permanent that player controls, that source deals double that damage … instead" (614.1, 614.12a). The two players are wave110a_pick's pair."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

def pair(plan: Plan, source_card: str | None) -> list[str]:
    """The two players the source chose as it entered (wave110a_pick.pair; a source that left the battlefield has no effect)."""
    from app.rules import wave110a_pick

    card = plan.state.cards.get(source_card or "")
    return wave110a_pick.pair(plan, source_card) if card is not None and card.zone.endswith(":battlefield") and source_card else []


def source_ok(plan: Plan, c: Any, ev: Any) -> bool:
    """The damage source's controller is one of the chosen players."""
    p = pair(plan, c.source_card)
    return (ev.get("src") or {}).get("controller") in p


def recipient_ok(plan: Plan, c: Any, ev: Any) -> bool:
    """The recipient is the other chosen player, or a permanent that player controls."""
    p = pair(plan, c.source_card)
    ctl = (ev.get("src") or {}).get("controller")
    if ctl not in p:
        return False
    other = p[1] if ctl == p[0] else p[0]
    target = ev["target"]
    if target in plan.state.players:
        return target == other
    card = plan.state.cards.get(target)
    return card is not None and card.zone.endswith(":battlefield") and card.controller == other
