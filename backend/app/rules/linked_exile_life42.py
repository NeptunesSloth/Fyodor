"""Exact native linked-exile payments and nominal life outcomes."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.rules import context, selectors
from app.rules import exile_packet_continuations as packets
from app.rules.plan import Plan


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text=packets.normalize(scripts.self_text(ability.text,ch.name))
    if text=='when ~ enters, for each opponent, exile up to one target nonland permanent that player controls until ~ leaves the battlefield':
        native=scripts.parse_effects('For each opponent, exile up to one target nonland permanent that player controls until ~ leaves the battlefield.')
        assert native is not None
        return {'kind':'triggered','trigger':'enters_self','optional':False,
                'effects':[{**effect,'link':True} for effect in native[0]],**scripts.target_fields(native[1])}
    if text=="{x}{w}: put target card with mana value x exiled with ~ into its owner's graveyard. you gain x life":
        selector=selectors.Selector(card=True,zones=('exile',),compare=(('mv','==',selectors.X_VALUE),)).key()
        return {'kind':'activated','cost':ability.cost,
                'effects':[{'do':'return_card','who':'target','to':'graveyard','under':'owner'},
                           {'do':'gain_life','who':'you','n':{'x':1}}],
                'target':{'what':'exiled_with:'+selector}}
    if text=='when ~ enters, for each opponent, exile up to one target creature that player controls and that player gains life equal to its power':
        native_definition=scripts.define(replace(ability,text='When ~ enters, for each opponent, exile up to one target creature that player controls.'),ch)
        assert native_definition is not None
        return {**native_definition,'effects':[{'do':'linked_exile_life42','who':'target:0','mode':'luminate'}]}
    return None


def run(plan: Plan, ctx: dict[str,Any], e: dict[str,Any]) -> bool:
    from app.rules import effects, values

    targets=effects._cards(plan,ctx,e['who'])
    if not targets:
        return True
    instructions: list[dict[str,Any]]=[]
    for index,cid in enumerate(targets):
        card=plan.state.cards[cid]
        beneficiary=card.controller
        binding='nominal_exile42_'+str(index)
        context.bind_objects(plan,ctx,binding,[cid])
        power=max(0,values.evaluate(plan,ctx,{'power':'ref:'+binding}))
        instructions += [{'do':'exile','who':'ref:'+binding},
                         {'do':'gain_life','who':'player:'+beneficiary,'n':power}]
    return packets.insert(ctx,instructions)


PRIMITIVES={'linked_exile_life42':run}
