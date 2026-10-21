"""A revealed creature enters attacking, then creates a genuine exact-pair reflexive fight."""
from __future__ import annotations

from typing import Any

from app.rules import context
from app.rules.plan import Plan


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    body=body.strip()
    body=body[:1].upper()+body[1:]
    if body == "Reveal the top card of your library. If it's a creature card, put it onto the battlefield tapped and attacking defending player or a planeswalker they control. Otherwise, put that card into your hand. When you put a creature card onto the battlefield this way, it fights ~.":
        return [{'do':'attack_reveal_fight'}],None,False
    return None


def reveal(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import reveal_outcomes

    if not reveal_outcomes.reveal_outcome_top(plan,ctx,{'do':'reveal_outcome_top','n':1,'player':'you',
                                                       'reveal':True,'exact_look':True}):
        return False
    ids=list(ctx.get('looked') or [])
    if not ids:
        return True
    cid=ids[0]
    key=f'attack_revealed_{ctx["next"]}'
    context.bind_objects(plan,ctx,key,[cid])
    steps: list[dict[str, Any]]
    if 'Creature' not in plan.ch(plan.state.cards[cid]).types:
        steps=[{'do':'rest_looked','to':'hand'}]
    else:
        steps=[{'do':'return_card','who':'ref:'+key,'to':'battlefield','under':'you','tapped':True,
                'attacking':True,'at':{'as':'that','planeswalkers':True},'as':key},
               {'do':'attack_reveal_reflexive','ref':key,'hans_oid':ctx.get('source_object')}]
    ctx['effects'][ctx['next']:ctx['next']]=steps
    return True


def reflexive(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import TriggerEvent
    from app.rules import trigger_multipliers, triggers

    entered=[cid for cid in context.objects(plan,ctx,e['ref']) if plan.state.cards[cid].zone.endswith(':battlefield')]
    if not entered:
        return True
    # The preceding native move succeeded. The two participants are fixed now;
    # neither a later blink nor a retargeted spell substitutes a new object.
    definition: dict[str, Any] = {'kind':'triggered','effects':[{'do':'fight','who':'object:'+plan.oid(entered[0]),
                                              'with':'object:'+(e.get('hans_oid') or '')}],
                'target':None,'optional':False}
    ref=context.ref_of(plan,entered[0])
    cause=TriggerEvent(kind='enter',objects=[ref] if ref is not None else [],count=1)
    triggers._add(plan,controller=ctx['controller'],source_card=ctx.get('source_card') or '',
                  source_object=ctx.get('source_object') or '',name=ctx.get('name') or '',
                  index=trigger_multipliers.REFLEXIVE,definition=definition,cause=cause)
    return True


PRIMITIVES={'attack_reveal_fight':reveal,'attack_reveal_reflexive':reflexive}
