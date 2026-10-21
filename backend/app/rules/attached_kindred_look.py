"""An optional native library look qualified by an Aura's exact enchanted object."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.game.rules_state import ObjectRef
from app.rules import context, selectors

if TYPE_CHECKING:
    from app.rules.plan import Plan

BODY = ("At the beginning of your upkeep, you may look at the top five cards of your library. "
        "If you do, you may put a creature card that shares a creature type with enchanted creature "
        "from among them onto the battlefield, then you put the rest of those cards on the bottom "
        "of your library in any order.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or scripts.self_text(ability.text, ch.name) != BODY:
        return None
    native = scripts.define(replace(ability, text='At the beginning of your upkeep, you may gain 1 life.'), ch)
    if native is None:
        return None
    return {**native, 'effects': [{'do':'attached_kindred_look'}]}


def capture(plan: Plan, definition: dict[str, Any], source: str) -> dict[str, Any]:
    if not any(e.get('do') == 'attached_kindred_look' for e in definition.get('effects') or []):
        return definition
    aura = next((c for c in plan.state.cards.values() if plan.oid(c)==source), None)
    host = plan.state.cards.get(aura.attached_to or '') if aura is not None else None
    host_ref = context.ref_of(plan,host.id) if host is not None else None
    ref = host_ref.model_dump(mode='json') if host_ref is not None else None
    return {**definition,'effects':[{**e,'host_ref':ref} if e.get('do')=='attached_kindred_look' else e for e in definition['effects']]}


def host_reference(plan: Plan,ctx: dict[str, Any],e: dict[str, Any]) -> ObjectRef | None:
    source = ctx.get('source_object') or ''
    aura = plan.state.cards.get(ctx.get('source_card') or '')
    if aura is not None and plan.oid(aura)==source and aura.zone.endswith(':battlefield'):
        return context.ref_of(plan,aura.attached_to) if aura.attached_to else None
    retained = plan.rules.last_attached_hosts.get(source)
    if retained is not None:
        return retained
    snap = plan.rules.lki.get(source)
    if snap is not None and snap.attached_to and snap.attached_object:
        host = plan.state.cards.get(snap.attached_to)
        zone = host.zone if host is not None and plan.oid(host)==snap.attached_object else f'{snap.controller}:battlefield'
        return ObjectRef(card=snap.attached_to,object_id=snap.attached_object,zone=zone)
    # Host departure clears the still-present Aura's attachment before its own
    # state-based graveyard move. Native detach receipts retain both old OIDs.
    event = next((v for v in reversed(plan.rules.events) if v.kind=='unattached' and v.object_id==source and v.by_card and v.source), None)
    if event is not None:
        host = plan.state.cards.get(event.by_card or '')
        zone = host.zone if host is not None and plan.oid(host)==event.source else f"{ctx['controller']}:battlefield"
        return ObjectRef(card=event.by_card or '',object_id=event.source or '',zone=zone)
    return ObjectRef.model_validate(e['host_ref']) if e.get('host_ref') else None


def prepare(plan: Plan,ctx: dict[str, Any],e: dict[str, Any]) -> bool:
    from app.rules.creature_types import CREATURE_TYPES

    ref = host_reference(plan,ctx,e)
    types: frozenset[str] = frozenset()
    if ref is not None:
        view = {**ctx,'refs':{'kindred_host':{'kind':'objects','objects':[ref.model_dump(mode='json')]}}}
        info = context.info(plan,view,'kindred_host')
        if info is not None:
            types = info[1].subtypes & CREATURE_TYPES
    sel = selectors.Selector(zones=('library',),card=True,types=('Creature',),subtypes=tuple(sorted(types)))
    if not types:
        sel = replace(sel,not_types=('Creature',))
    ctx['effects'][ctx['next']:ctx['next']] = [
        {'do':'look_top','player':'you','n':5,'exact_look':True},
        {'do':'pick_looked','n':1,'optional':True,'sel':sel.key(),'to':'battlefield','as':'kindred_selected'},
        {'do':'kindred_restore_unmoved'},
        {'do':'rest_looked','to':'bottom_any'}]
    return True


def restore_unmoved(plan: Plan,ctx: dict[str, Any],e: dict[str, Any]) -> bool:
    # A prohibited entry leaves the selected object in the looked-at library;
    # it remains part of 'the rest'. An exile replacement creates a new object.
    owner = ctx.get('looked_owner') or ctx['controller']
    for cid in context.objects(plan,ctx,'kindred_selected'):
        if plan.state.cards[cid].zone == f'{owner}:library' and cid not in ctx.get('looked',[]):
            ctx.setdefault('looked',[]).append(cid)
    return True


PRIMITIVES={'attached_kindred_look':prepare,'kindred_restore_unmoved':restore_unmoved}
