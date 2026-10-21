"""An attached artifact's controller is current information or exact-object LKI."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

TEXT = "At the beginning of your end step, this Aura deals 2 damage to enchanted artifact's controller."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or ability.text != TEXT:
        return None
    native = scripts.define(replace(ability, text=TEXT.replace("artifact's controller", "permanent's controller")), ch)
    if native is None:
        return None
    return {**native, 'effects': [{'do': 'attached_controller_damage67', 'n': 2}]}


def controller(plan: Plan, ctx: dict[str, Any]) -> str | None:
    source = plan.state.cards.get(ctx.get('source_card') or '')
    if (source is not None and source.zone.endswith(':battlefield')
            and plan.oid(source) == ctx.get('source_object')):
        host = plan.state.cards.get(source.attached_to or '')
        return host.controller if host is not None and host.zone.endswith(':battlefield') else None
    snap = plan.rules.lki.get(ctx.get('source_object') or '')
    if snap is None or snap.attached_object is None:
        return None
    host = plan.state.cards.get(snap.attached_to or '')
    if (host is not None and host.zone.endswith(':battlefield')
            and plan.oid(host) == snap.attached_object):
        return host.controller
    original = plan.rules.lki.get(snap.attached_object)
    return original.controller if original is not None else None


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    player = controller(plan, ctx)
    if player is None or player not in plan.live():
        return True
    return effects.damage(plan, ctx, {'do': 'damage', 'who': 'player:' + player, 'n': e['n']})


PRIMITIVES = {'attached_controller_damage67': run}
