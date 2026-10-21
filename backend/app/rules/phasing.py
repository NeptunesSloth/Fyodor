"""-- phasing (wave 13D) -- CR 702.26: "phase out" effects and the phasing keyword.

A phased-out permanent is treated as though it doesn't exist (702.26b) but didn't change zones (702.26d): it sits in
its controller's "phased" zone (app/game/handlers/cards.py ``phase_shift``), so every query over the battlefield skips
it, and the object keeps its identity, counters and tokens. Phasing events are no zone change (rules_state._diff).
Phasing in happens in the untap step of the player it phased out under (702.26a); with the keyword, the controller's
phased-in permanents with phasing phase out at the same time. A skipped untap step has no phasing event (702.26m).
"Whenever ~ phases in" (wave 50G, King of the Oathbreakers) is read; left manual: "whenever this phases out", "until ~ leaves", "can't phase in" wordings.
"""

from __future__ import annotations

from typing import Any

from app.game.state import zone_key
from app.rules.plan import Plan

Context = dict[str, Any]


def phase_out(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules.effects import _cards

    cards = [c for c in _cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")]
    if cards:
        plan.do({"type": "phase_shift", "card_ids": cards, "out": True}, actor=ctx["controller"])
    return True


def untap_step(plan: Plan, player: str) -> None:
    """702.26a: before ``player`` untaps, their phased-in permanents with phasing phase out and, simultaneously, the
    permanents that phased out under their control phase in (the ones phased out indirectly come along with their host)."""
    from app.rules import phase_lifetimes43

    state = plan.state
    out = [c for c in state.zones.get(zone_key(player, "battlefield"), []) if "phasing" in plan.ch(state.cards[c]).keywords]
    back = [c for c in state.zones.get(zone_key(player, "phased"), [])
            if not state.cards[c].phased_indirect and not phase_lifetimes43.held(plan, c)]
    if back:
        from app.game.rules_state import emit

        for c in back:  # -- trigger other (wave 50G) -- "Whenever ~ or another Spirit you control phases in" (King of the Oathbreakers): each one that phases in (ponytail: not an Aura or Equipment that comes along)
            emit(state, "designation", counter="phase_in", card=c, object_id=plan.oid(c), player=state.cards[c].controller)
        plan.do({"type": "phase_shift", "card_ids": back, "out": False}, actor=player)
        from app.rules import (
            keyword_actions,  # -- prepared (wave 13C) -- 722.3c: one that "phases in prepared" gets its copy anew
        )

        for c in state.zones.get(zone_key(player, "battlefield"), []):
            if plan.oid(c) in plan.rules.prepared:
                keyword_actions.become_prepared(plan, state.cards[c])
    if out:
        plan.do({"type": "phase_shift", "card_ids": out, "out": True}, actor=player)


PRIMITIVES = {"phase_out": phase_out}
