"""Unimported exact Surfer packet; conditional tapped status belongs to native entry."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.rules import delayed, selectors
from app.rules import exile_packet_continuations as packets
from app.rules.plan import Plan

TEXT="when ~ enters, exile any number of other target permanents you control. return those cards to the battlefield under their owner's control at the beginning of the next end step. if a land enters this way, it enters tapped"


def definition(ability: Any,ch: Any) -> dict[str,Any] | None:
    from app.rules import scripts

    if packets.normalize(scripts.self_text(ability.text,ch.name))!=TEXT:
        return None
    native=scripts.define(replace(ability,text='When this creature enters, draw a card.'),ch)
    parsed=scripts.parse_effects('Exile any number of target permanents you control.')
    assert native is not None and parsed is not None and isinstance(parsed[1],list)
    groups=[{**g,'what':selectors.replace(selectors.from_key(g['what']),other=True).key()} for g in parsed[1]]
    return {**native,**scripts.target_fields(groups),'effects':[{**parsed[0][0],'as':'surfer50'},
                              {'do':'surfer_prepare50','binding':'ref:surfer50'}]}



def prepare_return(plan: Plan,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    from app.rules import context

    key=e['binding'].removeprefix('ref:')
    actual=[cid for cid in context.objects(plan,ctx,key) if plan.state.cards[cid].zone.endswith(':exile')]
    if not actual:
        return True
    context.bind_objects(plan,ctx,key,actual)
    return packets.insert(ctx,delayed.wrap_when([{'do':'return_card','who':e['binding'],'to':'battlefield',
                                                'under':'owner','tapped_if_land':True}],delayed.WHEN['the next end step']))


PRIMITIVES={'surfer_prepare50':prepare_return}
