"""An attached artifact's controller is current information or exact-object LKI."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

HEX = "At the beginning of your upkeep, if enchanted Equipment is attached to a creature, destroy that creature."

TEXT = "At the beginning of your end step, this Aura deals 2 damage to enchanted artifact's controller."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    if ability.kind == 'triggered' and ability.text == HEX:
        native = scripts.define(replace(ability, text='At the beginning of your upkeep, draw a card.'), ch)
        if native is None:
            return None
        return {**native, 'if': {'object': 'host', 'is': selectors.Selector(extras=('attached_creature',)).key()},
                'effects': [{'do': 'host_creature_destroy67'}]}
    if ability.kind != 'triggered' or ability.text != TEXT:
        return None
    native = scripts.define(replace(ability, text=TEXT.replace("artifact's controller", "permanent's controller")), ch)
    if native is None:
        return None
    return {**native, 'effects': [{'do': 'attached_controller_damage67', 'n': 2}]}


def controller(plan: Plan, ctx: dict[str, Any]) -> str | None:
    from app.rules import attached_kindred_look

    reference = attached_kindred_look.host_reference(plan, ctx, {})
    if reference is None:
        return None
    host = plan.state.cards.get(reference.card)
    if (host is not None and host.zone.endswith(':battlefield')
            and plan.oid(host) == reference.object_id):
        return host.controller
    original = plan.rules.lki.get(reference.object_id)
    return original.controller if original is not None else None



def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    player = controller(plan, ctx)
    if player is None or player not in plan.live():
        return True
    return effects.damage(plan, ctx, {'do': 'damage', 'who': 'player:' + player, 'n': e['n']})


def destroy_host_creature(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects

    equipment = effects._cards(plan, ctx, 'host')
    if len(equipment) != 1:
        return True
    host = plan.state.cards.get(plan.state.cards[equipment[0]].attached_to or '')
    if host is None or not host.zone.endswith(':battlefield') or not plan.ch(host).is_creature:
        return True
    context.bind_objects(plan, ctx, 'hex67_creature', [host.id])
    return effects.destroy(plan, ctx, {'do': 'destroy', 'who': 'ref:hex67_creature'})


PRIMITIVES = {'attached_controller_damage67': run, 'host_creature_destroy67': destroy_host_creature}
