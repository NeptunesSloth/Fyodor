"""-- Chef's Kiss (wave 110D) -- "Gain control of target spell that targets only a single permanent or player. Copy it, then reselect the targets at random for the
spell and the copy. The new targets can't be you or a permanent you control."

110.2a/108.4 control of a spell changes its controller only (spell_control); 707.10 the copy is controlled by the new controller; 115.7 a new target must be legal for the spell
(its own restriction) and, here, neither the new controller nor a permanent that player controls; the pick is uniform over those (the old target may come up again).
If nothing is legal the target stays (115.7d, as for "choose new targets").
"""

from __future__ import annotations

from typing import Any

from app.rules.plan import Plan

LINE = ("Gain control of target spell that targets only a single permanent or player. Copy it, then reselect the targets at random for the spell and the copy. "
        "The new targets can't be you or a permanent you control.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import scripts

    d = scripts.define(replace(ability, text="Counter target spell that targets only a single permanent or player."), ch)
    if d is None:
        return None
    return {**d, "effects": [{"do": "gain_control_spell", "who": "target"}, {"do": "copy_spell", "who": "target"}, {"do": "reselect110d"}]}


def reselect(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    import secrets

    from app.rules import copying, stack_interaction, targets
    from app.rules.effects import target_refs

    me = ctx["controller"]
    orig = next((t["id"] for t in target_refs(ctx, "target") if t and t["id"] in plan.state.cards and plan.state.cards[t["id"]].zone == "stack"), None)
    if orig is None:
        return True
    stack = plan.state.zones.get("stack", [])
    copy = stack[-1] if stack and stack[-1] != orig else None  # the copy was put on top (707.10)
    rng = plan.rng or secrets.SystemRandom()
    for sid in (orig, copy):
        entry = stack_interaction.target_entry(plan, sid) if sid is not None else None
        if entry is None:
            continue
        pos = copying.positions(entry)
        legal = [x for x in stack_interaction._legal(plan, entry, pos[0], sid) if x != me
                 and not (x in plan.state.cards and plan.state.cards[x].controller == me and plan.state.cards[x].zone.endswith(":battlefield"))]
        new = None
        while legal and new is None:
            pick = legal.pop(rng.randrange(len(legal)))
            if copying._problem(plan, cand := copying._retargeted(entry, pos, [targets.ref(plan, pick)])) is None:
                new = cand
        stack_interaction._apply(plan, sid, new)
    return True


PRIMITIVES = {"reselect110d": reselect}
