"""Wave 110A: Aboleth Spawn - "Probing Telepathy — Whenever a creature entering under an opponent's control causes a triggered ability of that creature to
trigger, you may copy that ability. You may choose new targets for the copy."

603.2d / 603.3: the Spawn's ability triggers at the same time as the ability it copies (the pattern of Strict Proctor, wave110c_misc.proctor_triggers: the new
pending trigger is hooked from triggers.py right after the entering creature's own). It copies "that ability" (707.10) while it is still on the stack; the
shared link map ``proctor_links110c`` records the stack id the copied trigger got. 707.10c: new targets may be chosen for the copy."""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

TEXT = ("Whenever a creature entering under an opponent's control causes a triggered ability of that creature to trigger, you may copy that ability. "
        "You may choose new targets for the copy.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, wave110a

    if wave110a.strip_mode_label(scripts.self_text(ability.text, ch.name)) != TEXT:
        return None
    return {"kind": "static", "static": "spawn110a", "effects": []}  # read by :func:`triggers`, not by an event pass


def triggers(plan: Plan, pending: Any, cause: Any) -> None:
    """An entering creature caused ``pending`` (and its 603.2d copies) to trigger; each Aboleth Spawn whose controller is an opponent of the creature's controller
    triggers for each."""
    from app.game.rules_state import PendingTrigger
    from app.rules import scripts, trigger_multipliers

    src = plan.state.cards.get(pending.source_card or "")
    if cause is None or cause.kind != "enter" or src is None or not plan.ch(src).is_creature or src.id not in {o.card for o in cause.objects}:
        return
    for c in plan.state.cards.values():
        if c.controller == pending.controller or not c.zone.endswith(":battlefield") or not plan.in_game(c) or plan.manual(c) or c.face_down:
            continue
        if not any(d.get("static") == "spawn110a" for d in scripts.definitions(plan.ch(c)).values()):
            continue
        for p in [pending, *trigger_multipliers._extras(plan).get(pending.id, ([], 0))[0]]:
            plan.rules.proctor_links110c.setdefault(p.id, "")
            plan.rules.pending_triggers.append(PendingTrigger(
                id=secrets.token_hex(4), controller=c.controller, source_card=c.id, source_object=plan.oid(c), name=c.name,
                ability={"kind": "triggered", "optional": True, "effects": [{"do": "spawn_copy110a", "link": p.id}]}, key=f"spawn110a:{p.id}", event=cause))


def copy(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Copy the ability the creature's entering triggered (nothing if it has left the stack), then the new-targets choice."""
    sid = plan.rules.proctor_links110c.get(e["link"])
    if not sid or sid not in plan.state.cards or plan.state.cards[sid].zone != "stack":
        return True
    ctx["event"] = {**(ctx.get("event") or {}), "source": {"card": sid, "object_id": plan.oid(sid), "zone": "stack"}}
    ctx["effects"][ctx["next"]:ctx["next"]] = [{"do": "copy_ability", "who": "event_ability"}, {"do": "copy_new_targets", "optional": True}]
    return True


PRIMITIVES = {"spawn_copy110a": copy}
