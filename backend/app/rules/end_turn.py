"""-- end the turn (wave 46C) -- "End the turn." (Time Stop, Ultima, Sundial of the Infinite), "If it's your turn, end the turn." (Day's Undoing), "The player whose turn it is may end the turn." (Obeka).
Researched against CR 2026-09-25, rulings (Time Stop 2007-07-15, Ultima 2025-06-06, Day's Undoing 2017-04-18).

* 724.1a: triggered abilities that triggered before the process began but are not on the stack yet cease to exist (Ultima: the "dies" abilities of what it
  destroyed; Day's Undoing: what its shuffle and draws triggered).
* 724.1b: every object on the stack is exiled, the resolving one too (not countered: "can't be countered" does not matter); a copy or an ability just ceases to exist.
* 724.1c: state-based actions are checked, no player gets priority and nothing triggered goes on the stack. 724.1d: combat is left, the game goes straight to the
  cleanup step (the end step is skipped, 724.1e: its "at the beginning of the end step" abilities wait for the next turn's); the cleanup step then happens in
  its entirety (514), with a new one when something triggered during the process (724.1f, 514.3a).
* "The player whose turn it is may end the turn." (Obeka, Brute Chronologist): that player decides (608.2d), whoever controls the ability. Instructions after
  "End the turn." (Glorious End's delayed loss at the controller's next end step) are carried out afterwards as written (the ruling says the spell keeps resolving).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.state import COMBAT_PHASES, STACK

if TYPE_CHECKING:
    from app.rules.plan import Plan

TEMPLATES: list[tuple[re.Pattern[str], Any]] = [
    (re.compile(r"^end the turn$", re.IGNORECASE), lambda m: ([{"do": "end_turn"}], None)),
    (re.compile(r"^the player whose turn it is may end the turn$", re.IGNORECASE), lambda m: ([{"do": "end_turn", "ask": "active"}], None)),  # (Obeka: that player decides, 608.2d)
]


def end_turn(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """724.1: the expedited process; False while the cleanup step waits for the active player's discard."""
    from app.game.rules_state import DecisionOption
    from app.rules import combat, engine, sba, triggers
    from app.rules.plan import decide

    r = plan.rules
    if e.get("ask") and not e.get("asked"):  # "The player whose turn it is may end the turn." (Obeka, Brute Chronologist): they decide, whoever controls the ability
        decide(plan, player=plan.active, kind="confirm", prompt=f"{ctx.get('name') or 'An ability'}: end the turn?",
               options=[DecisionOption(id="yes", label="End the turn"), DecisionOption(id="no", label="Don't")], resume={"step": "end_turn_ask", "ctx": ctx})
        return False
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


def resume_ask(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    if chosen[0] == "yes" and not end_turn(plan, ctx, {"asked": True}):
        return  # (the cleanup step waits for a discard)
    effects.continue_effects(plan, ctx)


PRIMITIVES = {"end_turn": end_turn}
RESUME = {"end_turn_ask": resume_ask}
