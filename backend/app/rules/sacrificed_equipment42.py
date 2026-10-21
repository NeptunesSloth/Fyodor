"""Exact prior attachment objects for a sacrificed source's Equipment transfer."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'sacrificed_equipment42'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    text = body.strip()
    text = text[:1].upper() + text[1:]
    if text != ('Target creature you control gains indestructible until end of turn. Put ~\'s counters on that creature '
                'and attach an Equipment that was attached to ~ to that creature.'):
        return None
    first = scripts.parse_effects('Target creature you control gains indestructible until end of turn.')
    if first is None:
        return None
    return ([*first[0], {'do': 'lki_counters', 'from': 'self', 'who': 'target'}, {'do': STEP}], first[1], False)


def attach_prior(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import attachments, effects
    from app.rules.plan import decide

    targets = effects._cards(plan, ctx, 'target')
    if not targets:
        return True
    snap = plan.rules.lki.get(ctx.get('source_object') or '')
    if snap is None or not snap.attached_objects_known:
        decide(plan, player=ctx['controller'], kind='manual_resolution',
               prompt='This older save has no record of the original Equipment objects. Resolve the attachment manually.',
               options=[DecisionOption(id='done', label='Done')], resume={'step': STEP, 'ctx': ctx, 'legacy': True})
        return False
    offered = []
    for cid, oid in snap.attached_objects.items():
        card = plan.state.cards.get(cid)
        if (card is not None and plan.oid(card) == oid and card.zone.endswith(':battlefield')
                and 'Equipment' in plan.ch(card).subtypes and attachments.host_problem(plan, card, targets[0]) is None):
            offered.append(DecisionOption(id=cid, label=card.name or 'Equipment', card_id=cid))
    if not offered:
        return True
    decide(plan, player=ctx['controller'], kind='choose_one', prompt='Choose an Equipment that was attached to the sacrificed creature',
           options=offered, resume={'step': STEP, 'ctx': ctx, 'objects': snap.attached_objects,
                                   'target': {'card': targets[0], 'object_id': plan.oid(targets[0])}})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import attachments, effects

    if len(chosen) != 1 or chosen[0] not in {o.id for o in d.options}:
        raise ActionError('Choose an offered Equipment')
    r = d.resume
    if not r.get('legacy'):
        cid = chosen[0]
        card = plan.state.cards.get(cid)
        target = plan.state.cards.get(r['target']['card'])
        if (card is not None and plan.oid(card) == r['objects'][cid] and target is not None
                and plan.oid(target) == r['target']['object_id']):
            attachments.attach(plan, cid, target.id, r['ctx']['controller'])
    effects.continue_effects(plan, r['ctx'])


PRIMITIVES = {STEP: attach_prior}
RESUME = {STEP: resume}
