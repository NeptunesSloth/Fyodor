"""Unimported exact self-exile delayed return with permanent haste."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.rules import delayed
from app.rules import exile_packet_continuations as packets
from app.rules.plan import Plan

OBZEDAT="at the beginning of your end step, you may exile ~. if you do, return it to the battlefield under its owner's control at the beginning of your next upkeep. it gains haste"


def definition(ability: Any,ch: Any) -> dict[str,Any] | None:
    from app.rules import scripts

    text=packets.normalize(scripts.self_text(ability.text,ch.name))
    if text==OBZEDAT:
        native=scripts.define(replace(ability,text='At the beginning of your end step, draw a card.'),ch)
        assert native is not None
        return {**native,'optional':True,'effects':[{'do':'exile','who':'self','as':'blink50'},
            {'do':'self_blink_prepare50','binding':'ref:blink50','when':delayed.WHEN['your next upkeep'],'haste':True}]}
    return None


def prepare_return(plan: Plan,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    from app.rules import context

    key=e['binding'].removeprefix('ref:')
    actual=[cid for cid in context.objects(plan,ctx,key) if plan.state.cards[cid].zone.endswith(':exile')]
    if not actual:
        return True
    context.bind_objects(plan,ctx,key,actual)
    following=[{'do':'return_card','who':e['binding'],'to':'battlefield','under':'owner',**({'as':key} if e.get('haste') else {})}]
    if e.get('haste'):
        following.append({'do':'grant','who':e['binding'],'keywords':['haste'],'duration':'permanent'})
    return packets.insert(ctx,delayed.wrap_when(following,e['when']))


PRIMITIVES={'self_blink_prepare50':prepare_return}
