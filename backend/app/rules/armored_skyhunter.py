"""Private Aura/Equipment look, native entry, optional attachment, and random rest."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import Decision, DecisionOption, ObjectRef
from app.game.state import zone_key
from app.rules import context

if TYPE_CHECKING:
    from app.rules.plan import Plan

_TEXT = ('Look at the top six cards of your library. You may put an Aura or Equipment card from among them onto the battlefield. '
         'If an Equipment is put onto the battlefield this way, you may attach it to a creature you control. '
         'Put the rest of those cards on the bottom of your library in a random order.')
_KEY = 'armored_skyhunter'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    if body.strip().casefold() == _TEXT.casefold():
        return [{'do': _KEY}, {'do': _KEY + '_attach'}, {'do': _KEY + '_rest'}], None, False
    return None


def begin(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules.plan import decide

    pid = ctx['controller']
    ids = plan.state.zones.get(zone_key(pid, 'library'), [])[:6] if pid in plan.live() else []
    refs = [r.model_dump(mode='json') for cid in ids if (r := context.ref_of(plan, cid)) is not None]
    ctx[_KEY] = {'looked': refs, 'look_open': bool(ids)}
    if not ids:
        return True
    plan.do({'type': 'look_top', 'player': pid, 'count': len(ids)}, actor=pid)
    choices = [cid for cid in ids if plan.ch(plan.state.cards[cid]).subtypes & {'Aura', 'Equipment'}]
    if not choices:
        return True
    decide(plan, player=pid, kind='choose_cards', prompt='You may put an Aura or Equipment onto the battlefield',
           options=[DecisionOption(id=cid, label=plan.state.cards[cid].name or 'Card', card_id=cid) for cid in choices],
           min_choices=0, max_choices=1, resume={'step': _KEY, 'ctx': ctx})
    return False


def resume_pick(plan: Plan, d: Decision, chosen: list[str]) -> None:
    from app.rules import attachments, effects

    assert d.resume is not None
    ctx = d.resume['ctx']
    if chosen:
        saved = next((r for r in ctx[_KEY]['looked'] if r['card'] == chosen[0]), None)
        card = context._same(plan, ObjectRef.model_validate(saved)) if saved else None
        if card is not None and card.zone == zone_key(d.player, 'library'):
            ctx[_KEY]['selected'] = saved
            if not attachments.enter(plan, [{'card': card.id, 'player': d.player, 'actor': d.player}], ctx):
                return
    effects.continue_effects(plan, ctx)


def attach_equipment(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import attachments
    from app.rules.plan import decide

    selected = (ctx.get(_KEY) or {}).get('selected')
    if not selected:
        return True
    card = plan.state.cards.get(selected['card'])
    pid = ctx['controller']
    if (card is None or not card.zone.endswith(':battlefield') or not plan.in_game(card)
            or 'Equipment' not in plan.ch(card).subtypes or not any(
                event.kind == 'zone_change' and event.object_id == selected['object_id']
                and event.new_object_id == plan.oid(card) for event in plan.rules.events)):
        return True
    hosts = [c for c in plan.state.cards.values() if c.controller == pid and c.zone.endswith(':battlefield')
             and plan.in_game(c) and plan.ch(c).is_creature and attachments.host_problem(plan, card, c.id) is None]
    if not hosts:
        return True
    equipment_ref = context.ref_of(plan, card.id)
    if equipment_ref is None:
        return True
    host_refs = {c.id: ref.model_dump(mode='json') for c in hosts if (ref := context.ref_of(plan, c.id)) is not None}
    decide(plan, player=pid, kind='choose_one', prompt='You may attach the Equipment to a creature you control',
           options=[DecisionOption(id='no', label="Don't attach"),
                    *[DecisionOption(id=c.id, label=c.name or 'Creature', card_id=c.id) for c in hosts]],
           resume={'step': _KEY + '_attach', 'ctx': ctx,
                   'equipment': equipment_ref.model_dump(mode='json'), 'hosts': host_refs})
    return False


def resume_attach(plan: Plan, d: Decision, chosen: list[str]) -> None:
    from app.rules import attachments, effects

    assert d.resume is not None
    ctx = d.resume['ctx']
    card = context._same(plan, ObjectRef.model_validate(d.resume['equipment']))
    saved = d.resume['hosts'].get(chosen[0]) if chosen else None
    host = context._same(plan, ObjectRef.model_validate(saved)) if saved else None
    if card is not None and host is not None and host.controller == d.player:
        attachments.attach(plan, card.id, host.id, d.player)
    effects.continue_effects(plan, ctx)


def rest(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    data = ctx.pop(_KEY, {})
    pid = ctx['controller']
    if data.get('look_open') and pid in plan.live():
        plan.do({'type': 'end_view', 'zone': 'library'}, actor=pid)
    cards = [card.id for ref in data.get('looked', []) if (card := context._same(plan, ObjectRef.model_validate(ref))) is not None
             and card.zone == zone_key(pid, 'library')]
    if cards and pid in plan.live():
        effects.bottom_at_random(plan, pid, cards)
    return True


PRIMITIVES = {_KEY: begin, _KEY + '_attach': attach_equipment, _KEY + '_rest': rest}
RESUME = {_KEY: resume_pick, _KEY + '_attach': resume_attach}
