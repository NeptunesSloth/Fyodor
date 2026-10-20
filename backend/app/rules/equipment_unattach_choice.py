"""Optional, untargeted Equipment removal with an exact host continuation."""
from __future__ import annotations

from typing import Any

from app.game.rules_state import DecisionOption
from app.rules.plan import Plan, decide

_BODY = ('You may unattach an Equipment from a creature you control. '
         'If you do, tap that creature and it gains indestructible until end of turn.')


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    return ([{'do': 'equipment_unattach_choice'}], None, False) if body.strip() == _BODY else None


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    candidates = {}
    for equipment in plan.state.cards.values():
        host = plan.state.cards.get(equipment.attached_to or '')
        if (equipment.zone.endswith(':battlefield') and 'Equipment' in plan.ch(equipment).subtypes
                and host is not None and host.zone.endswith(':battlefield')
                and host.controller == ctx['controller'] and 'Creature' in plan.ch(host).types):
            candidates[equipment.id] = {'equipment': plan.oid(equipment), 'host': host.id, 'host_oid': plan.oid(host)}
    if not candidates:
        return True
    decide(plan, player=ctx['controller'], kind='choose_cards', prompt='You may unattach an Equipment',
           options=[DecisionOption(id=cid, label=plan.state.cards[cid].name or 'Equipment', card_id=cid) for cid in candidates],
           min_choices=0, max_choices=1,
           resume={'step': 'equipment_unattach_choice', 'ctx': ctx, 'candidates': candidates})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import context, effects

    ctx = d.resume['ctx']
    if chosen:
        cid = chosen[0]
        original = d.resume['candidates'][cid]
        equipment = plan.state.cards.get(cid)
        host = plan.state.cards.get(original['host'])
        if (equipment is not None and host is not None and plan.oid(equipment) == original['equipment']
                and plan.oid(host) == original['host_oid'] and equipment.attached_to == host.id
                and host.controller == ctx['controller'] and host.zone.endswith(':battlefield')
                and 'Creature' in plan.ch(host).types):
            context.bind_objects(plan, ctx, 'unattached_host', [host.id])
            plan.do({'type': 'detach', 'card_ids': [cid]}, actor=ctx['controller'])
            steps = [{'do': 'tap', 'who': 'ref:unattached_host'},
                     {'do': 'grant', 'who': 'ref:unattached_host', 'keywords': ['indestructible']}]
            ctx['effects'][ctx['next']:ctx['next']] = steps
    effects.continue_effects(plan, ctx)


PRIMITIVES = {'equipment_unattach_choice': run}
RESUME = {'equipment_unattach_choice': resume}
