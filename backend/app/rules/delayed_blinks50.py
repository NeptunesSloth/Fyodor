"""Unimported exact blink recipes; native exile and delayed object receipts."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.rules import delayed, selectors
from app.rules import exile_packet_continuations as packets
from app.rules.plan import Plan

YORION='when ~ enters, exile any number of other nonland permanents you own and control. return those cards to the battlefield at the beginning of the next end step'
NAHIRI="at the beginning of your end step, exile any number of nontoken artifacts and/or creatures you control. return those cards to the battlefield under their owner's control at the beginning of your next upkeep"
SUDDEN="exile all nonland permanents target player controls. return the exiled cards to the battlefield under their owner's control at the beginning of the next end step"


def _return(when: dict[str,Any]) -> list[dict[str,Any]]:
    return [{'do':'blink_prepare50','binding':'ref:blink50','when':when}]


def _choose(sel: selectors.Selector,when: dict[str,Any]) -> list[dict[str,Any]]:
    key=sel.key()
    return [{'do':'sacrifice_choice','who':'you','sel':key,'n':{'count':key},'upto':True,'exile':True,'as':'blink50'},*_return(when)]


def definition(ability: Any,ch: Any) -> dict[str,Any] | None:
    from app.rules import scripts

    text=packets.normalize(scripts.self_text(ability.text,ch.name))
    if text==YORION:
        native=scripts.define(replace(ability,text='When this creature enters, draw a card.'),ch)
        assert native is not None
        return {**native,'effects':[{'do':'yorion_choose50'}]}
    if text==NAHIRI:
        native=scripts.define(replace(ability,text='At the beginning of your end step, draw a card.'),ch)
        assert native is not None
        return {**native,'effects':_choose(selectors.Selector(controller='you',token=False,types=('Artifact','Creature')),delayed.WHEN['your next upkeep'])}
    return None


def prepare_return(plan: Plan,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    from app.rules import context

    key=e['binding'].removeprefix('ref:')
    actual=[cid for cid in context.objects(plan,ctx,key) if plan.state.cards[cid].zone.endswith(':exile')]
    if not actual:
        return True
    context.bind_objects(plan,ctx,key,actual)
    return packets.insert(ctx,delayed.wrap_when([{'do':'return_card','who':e['binding'],'to':'battlefield','under':'owner'}],e['when']))


def choose_yorion(plan: Plan,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    from app.game.errors import ActionError

    source=ctx.get('source_object')
    if not source:
        raise ActionError('The original blink source object is unavailable')
    sel=selectors.Selector(controller='you',owner='you',not_types=('Land',),extras=('not_oid:'+source,))
    return packets.insert(ctx,_choose(sel,delayed.WHEN['the next end step']))


PRIMITIVES={'blink_prepare50':prepare_return,'yorion_choose50':choose_yorion}


def parse(body: str) -> tuple[list[dict[str,Any]],Any,bool] | None:
    from app.rules import scripts

    text=packets.normalize(body)
    if text==SUDDEN:
        native=scripts.parse_effects('Exile all nonland permanents target player controls.')
    elif text=="exile up to one target creature or land you control. if you do, return it to the battlefield under its owner's control at the beginning of the next end step":
        native=scripts.parse_effects('Exile up to one target creature or land you control.')
    else:
        return None
    assert native is not None
    effects,target,optional=native
    return [{**effects[0],'as':'blink50'},*_return(delayed.WHEN['the next end step'])],target,optional
