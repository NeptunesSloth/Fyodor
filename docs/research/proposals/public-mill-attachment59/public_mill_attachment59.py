"""Public milled-card payments and optional exact Equipment attachment continuations."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
_AIR = "Mill three cards. You may put a Plains card or a creature card with mana value 3 or less from among the cards milled this way into your hand. If you don't, put a +1/+1 counter on ~."
_REQUEST = 'Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn. You may attach an Equipment you control to that creature. If you do, unattach it at the beginning of the next end step.'


def parse(body: str, it: str | None, event_player: bool) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts, selectors

    text = body.strip()
    text = text[:1].upper() + text[1:]
    if text == _AIR:
        public = ('graveyard', 'exile', 'battlefield', 'command', 'stack')
        plains = selectors.Selector(card=True, zones=public, subtypes=('Plains',))
        creature = selectors.Selector(card=True, zones=public, types=('Creature',), compare=(('mv', '<=', 3),))
        sel = selectors.Selector(card=True, zones=public, either=(plains.key(), creature.key()))
        return [
            {'do': 'mill', 'who': 'you', 'n': 3, 'as': 'milled59'},
            {'do': 'pick_looked', 'who': 'ref:milled59', 'public_mill59': True, 'choice_payment59': True,
             'n': 1, 'sel': sel.key(), 'to': 'hand', 'optional': True, 'did': 'picked59'},
            {'do': 'only_if', 'cond': {'not': {'succeeded': 'picked59'}}, 'skip': 1},
            {'do': 'add_counters', 'who': 'self', 'kind': '+1/+1', 'n': 1},
        ], None, False
    if text == _REQUEST:
        first = scripts.parse_effects('Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn.', it, event_player=event_player)
        if first is not None and not first[2]:
            return [*first[0], {'do': 'request_attach59', 'who': 'target'}], first[1], False
    return None


def prepare_public_mill(plan: Plan, ctx: Context, e: dict[str, Any]) -> None:
    from app.rules import effects

    selected = effects._cards(plan, ctx, e['who'])
    selected = [cid for cid in selected if plan.state.cards[cid].zone.rsplit(':', 1)[-1]
                in ('graveyard', 'exile', 'battlefield', 'command', 'stack') and not plan.state.cards[cid].face_down]
    ctx['looked'], ctx['looked_zone'], ctx['looked_owner'] = selected, 'public_milled59', ctx['controller']
    ctx['looked_objects'] = {cid: plan.oid(plan.state.cards[cid]) for cid in selected}


def looked(plan: Plan, ctx: Context) -> tuple[str, list[str]]:
    return ctx['looked_owner'], [cid for cid in ctx.get('looked') or [] if cid in plan.state.cards
                                and plan.state.cards[cid].zone.rsplit(':', 1)[-1] in ('graveyard', 'exile', 'battlefield', 'command', 'stack')
                                and not plan.state.cards[cid].face_down
                                and (ctx.get('looked_objects') or {}).get(cid) == plan.oid(plan.state.cards[cid])]


def choose_attachment(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import attach_entry

    done = attach_entry.choose(plan, ctx, {'who': e['who'], 'kinds': ['Equipment'], 'n': 1, 'optional': True})
    if not done:
        decision = plan.rules.decision
        assert decision is not None and decision.resume is not None
        assert decision.resume.get('step') == 'attach_choose'
        decision.resume['step'] = 'request_attach59'
        decision.resume['host_oid59'] = plan.oid(plan.state.cards[decision.resume['host']])
        decision.resume['equipment_oids59'] = {o.id: plan.oid(plan.state.cards[o.id]) for o in decision.options}
    return done


def resume_attachment(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import attachments, context, effects

    ctx, host = d.resume['ctx'], plan.state.cards.get(d.resume['host'])
    if chosen and host is not None and plan.oid(host) == d.resume['host_oid59'] and host.zone.endswith(':battlefield'):
        cid = chosen[0]
        equipment = plan.state.cards.get(cid)
        if equipment is not None and plan.oid(equipment) == d.resume['equipment_oids59'].get(cid):
            attachments.attach(plan, cid, host.id, d.player)
            if equipment.attached_to == host.id:
                context.bind_objects(plan, ctx, 'equipment59', [cid])
                ctx['effects'][ctx['next']:ctx['next']] = [
                    {'do': 'delayed', 'when': {'kind': 'step', 'step': 'end', 'whose': 'next'}, 'n': 1},
                    {'do': 'request_unattach59', 'who': 'ref:equipment59'},
                ]
    effects.continue_effects(plan, ctx)


def unattach(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import effects

    cards = [cid for cid in effects._cards(plan, ctx, e['who']) if plan.state.cards[cid].zone.endswith(':battlefield')]
    if cards:
        plan.do({'type': 'detach', 'card_ids': cards}, actor=ctx['controller'])
    return True


PRIMITIVES = {'request_attach59': choose_attachment, 'request_unattach59': unattach}
RESUME = {'request_attach59': resume_attachment}
