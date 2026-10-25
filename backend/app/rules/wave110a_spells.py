"""-- spells (wave 110A) -- instant and sorcery wordings read onto the existing primitives."""
from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

Parsed = tuple[list[dict[str, Any]], Any, bool]


def _p(text: str) -> Parsed:
    from app.rules import scripts

    got = scripts.parse_effects(text)
    if got is None:
        raise AssertionError(f"wave110a: the grammar no longer reads {text!r}")
    return copy.deepcopy(got)


def _berserk() -> Parsed:
    """Berserk: "that creature attacked this turn" is read as the end step begins (508.1; the attack record of that object, 400.7)."""
    effects, target, optional = _p("Target creature gains trample and gets +X/+0 until end of turn, where X is its power. "
                                   "At the beginning of the next end step, destroy that creature.")
    destroy, delayed = effects.pop(), effects[-1]
    cond = {"history": "object", "object": "ref:berserk110a", "what": "attacked"}
    return [*effects[:-1], {"do": "bind110a", "who": "target", "as": "berserk110a"}, {**delayed, "n": 2},
            {"do": "deferred:only_if", "cond": cond, "skip": 1}, destroy], target, optional


BUILDERS: dict[str, Callable[[], Parsed]] = {
    "End the combat phase.": lambda: ([{"do": "end_combat_phase110a"}], None, False),  # (Mandate of Peace: 724.2)
    "Target creature gains trample and gets +X/+0 until end of turn, where X is its power. At the beginning of the next end step, destroy that "
    "creature if it attacked this turn.": _berserk,
}


def bind(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Name the objects ``who`` is now (400.7), so a condition of a delayed trigger can ask about them."""
    from app.rules import context, effects

    context.bind_objects(plan, ctx, e["as"], effects._cards(plan, ctx, e["who"]))
    return True


def end_combat_phase(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """724.2: the expedited process, as end_turn.end_turn (724.1) but to the next phase (the postcombat main, or an added phase): earlier triggers
    that weren't on the stack cease to exist (724.2a), the stack is exiled with the resolving spell (724.2b), state-based actions (724.2c), combat is
    left and "until end of combat" effects expire (724.2d), no end of combat step so its abilities don't trigger (724.2e); outside a combat phase
    nothing happens (724.2g)."""
    from app.game.state import COMBAT_PHASES, STACK
    from app.rules import combat, combat_rules, engine, sba, triggers

    if plan.state.turn.phase not in COMBAT_PHASES:
        return True
    r = plan.rules
    triggers.collect(plan)
    r.pending_triggers = []
    for sid in list(plan.state.zones.get(STACK, [])):
        oid = plan.oid(sid)
        r.stack.pop(sid, None)
        r.buyback = [o for o in r.buyback if o != oid]
        r.flashback = [o for o in r.flashback if o != oid]
        r.exile_resolves.pop(oid, None)
        plan.do({"type": "move", "card_ids": [sid], "to": {"player": plan.state.cards[sid].owner, "zone": "exile"}}, actor=ctx["controller"])
    plan.note(f"{ctx.get('name') or 'An effect'} ends the combat phase (724.2)", actor=ctx["controller"])
    sba.check(plan)
    combat.end_combat(plan)
    engine.empty_pools(plan)
    plan.do({"type": "phase", "to": combat_rules.next_phase(plan) or "main2", "force": True}, actor=plan.active)
    engine._mark_step(plan)
    engine.on_step_start(plan)
    return r.decision is None


PRIMITIVES = {"bind110a": bind, "end_combat_phase110a": end_combat_phase}
