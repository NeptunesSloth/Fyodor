"""Unimported exact next-combat blink; native delayed return and temporary haste."""
from __future__ import annotations

from typing import Any

from app.rules import delayed
from app.rules import exile_packet_continuations as packets
from app.rules.plan import Plan

TEXT="exile all creatures you control. at the beginning of the next combat, return those cards to the battlefield under their owner's control and those creatures gain haste until end of turn"


def parse(body: str) -> tuple[list[dict[str,Any]],Any,bool] | None:
    from app.rules import scripts

    if packets.normalize(body)!=TEXT:
        return None
    native=scripts.parse_effects('Exile all creatures you control.')
    assert native is not None
    effects,target,optional=native
    return [{**effects[0],'as':'combat_blink50'},{'do':'combat_blink_prepare50','binding':'ref:combat_blink50'}],target,optional


def prepare_return(plan: Plan,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    from app.rules import context

    key=e['binding'].removeprefix('ref:')
    actual=[cid for cid in context.objects(plan,ctx,key) if plan.state.cards[cid].zone.endswith(':exile')]
    if not actual:
        return True
    context.bind_objects(plan,ctx,key,actual)
    following=[{'do':'return_card','who':e['binding'],'to':'battlefield','under':'owner','as':key},
               {'do':'grant','who':e['binding'],'keywords':['haste'],'duration':'end_of_turn'}]
    return packets.insert(ctx,delayed.wrap_when(following,{'kind':'step','step':'begin_combat','whose':'next'}))


PRIMITIVES={'combat_blink_prepare50':prepare_return}
