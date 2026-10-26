"""-- Firebender Ascension (wave 110D) -- "Whenever a creature you control attacking causes a triggered ability of that creature to trigger, put a quest counter on this
enchantment. Then if it has four or more quest counters on it, you may copy that ability. You may choose new targets for the copy."

603.2, 603.2d: like Strict Proctor (wave110c_misc.proctor_triggers) the Ascension triggers at the same time as each ability the attack caused (its 603.2d extra copies
too); the ability it copies is the one on the stack once they are put there (707.10c new targets).
"""

from __future__ import annotations

import secrets
from typing import Any

from app.rules.plan import Plan

LINE = ("Whenever a creature you control attacking causes a triggered ability of that creature to trigger, put a quest counter on ~. "
        "Then if ~ has four or more quest counters on ~, you may copy that ability. You may choose new targets for the copy.")


def triggers(plan: Plan, pending: Any, cause: Any) -> None:
    from app.game.rules_state import PendingTrigger
    from app.rules import scripts, trigger_multipliers

    if cause is None or cause.kind != "attack" or not any(r.card == pending.source_card for r in cause.objects):
        return
    for c in plan.state.cards.values():
        if (not c.zone.endswith(":battlefield") or c.controller != pending.controller or not plan.in_game(c) or plan.manual(c) or c.face_down
                or not any(d.get("static") == "firebender110d" for d in scripts.definitions(plan.ch(c)).values())):
            continue
        for p in [pending, *trigger_multipliers._extras(plan).get(pending.id, ([], 0))[0]]:
            plan.rules.proctor_links110c.setdefault(p.id, "")
            plan.rules.pending_triggers.append(PendingTrigger(
                id=secrets.token_hex(4), controller=c.controller, source_card=c.id, source_object=plan.oid(c), name=c.name, key=f"firebender110d:{p.id}", event=cause,
                ability={"kind": "triggered", "effects": [
                    {"do": "add_counters", "who": "self", "kind": "quest", "n": 1},
                    {"do": "only_if", "cond": {"value": {"counters": "quest", "on": "self"}, "op": ">=", "n": 4}, "skip": 3},
                    {"do": "may_rest", "label": "Copy that ability"},
                    {"do": "firebender_copy110d", "link": p.id}]}))


def copy(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Copy the linked ability if it is still the object on the stack; the copy may get new targets (707.10c). The ability that left the stack leaves nothing to copy."""
    from app.rules import copying

    sid = plan.rules.proctor_links110c.get(e["link"])
    if not sid or sid not in plan.state.cards or plan.state.cards[sid].zone != "stack":
        return True
    return copying.run(plan, copying.new_job(ctx, controller=ctx["controller"], objects=[(sid, plan.oid(sid), 1)], retarget=True, label=ctx.get("name") or "Copy"))


PRIMITIVES = {"firebender_copy110d": copy}
