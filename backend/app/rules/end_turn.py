"""-- end the turn (wave 46C) -- "End the turn." (Time Stop, Ultima, Sundial of the Infinite), "If it's your turn, end the turn." (Day's Undoing).
Researched against CR 2026-09-25, rulings (Time Stop 2007-07-15, Ultima 2025-06-06, Day's Undoing 2017-04-18).

* 724.1a: triggered abilities that triggered before the process began but are not on the stack yet cease to exist (Ultima: the "dies" abilities of what it
  destroyed; Day's Undoing: what its shuffle and draws triggered).
* 724.1b: every object on the stack is exiled, the resolving one too (not countered: "can't be countered" does not matter); a copy or an ability just ceases to exist.
* 724.1c: state-based actions are checked, no player gets priority and nothing triggered goes on the stack. 724.1d: combat is left, the game goes straight to the
  cleanup step (the end step is skipped, 724.1e: its "at the beginning of the end step" abilities wait for the next turn's); the cleanup step then happens in
  its entirety (514), with a new one when something triggered during the process (724.1f, 514.3a).
Refused (manual): "The player whose turn it is may end the turn." (Obeka: another player decides), an end the turn with other instructions after it
(Glorious End's delayed loss) - they stay unparsed lines.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.state import COMBAT_PHASES, STACK

if TYPE_CHECKING:
    from app.rules.plan import Plan

TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(re.compile(r"^end the turn$", re.IGNORECASE), lambda m: ([{"do": "end_turn"}], None))]


def end_turn(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """724.1: the expedited process; False while the cleanup step waits for the active player's discard."""
    from app.rules import combat, engine, sba, triggers

    r = plan.rules
    triggers.collect(plan)
    r.pending_triggers = []  # 724.1a
    for sid in list(plan.state.zones.get(STACK, [])):  # 724.1b
        card = plan.state.cards[sid]
        oid = plan.oid(sid)
        r.stack.pop(sid, None)
        r.buyback = [o for o in r.buyback if o != oid]
        r.flashback = [o for o in r.flashback if o != oid]
        r.exile_resolves.pop(oid, None)
        plan.do({"type": "move", "card_ids": [sid], "to": {"player": card.owner, "zone": "exile"}}, actor=ctx["controller"])
    plan.note(f"{ctx.get('name') or 'An effect'} ends the turn (724.1)", actor=ctx["controller"])
    sba.check(plan)  # 724.1c
    if plan.state.turn.phase in COMBAT_PHASES:  # 724.1d
        combat.end_combat(plan)
    engine.empty_pools(plan)
    plan.do({"type": "phase", "to": "cleanup", "force": True}, actor=plan.active)
    engine._mark_step(plan)
    engine.on_step_start(plan)
    return r.decision is None


PRIMITIVES = {"end_turn": end_turn}
