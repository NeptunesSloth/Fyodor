"""Paid-color outcomes compose native instructions without changing target legality."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText
    from app.rules.plan import Plan
    from app.rules.scripts import Definition

Parsed = tuple[list[dict[str, Any]], Any, bool, str]


def native(text: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts
    return scripts.parse_effects(text)


def paid(symbols: str) -> dict[str, Any]:
    return {'object': 'self', 'cast': {'spent': {c: symbols.count(c) for c in set(symbols)}}}


def gate(symbols: str, es: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{'do': 'only_if', 'cond': paid(symbols), 'skip': len(es)}, *es]


def build(body: str) -> Parsed | None:
    text = re.sub(r'\s+', ' ', body.strip())
    text = text[:1].upper() + text[1:]
    normal = {
        'Prevent all combat damage that would be dealt this turn if {W} was spent to cast this spell. Each player loses 1 life for each attacking creature they control if {B} was spent to cast this spell.': 'If {W} was spent to cast this spell, prevent all combat damage that would be dealt this turn. If {B} was spent to cast this spell, each player loses 1 life for each attacking creature they control.',
        'Return up to one target creature card from your graveyard to the battlefield if {B} was spent to cast this spell. Creatures target player controls get +2/+0 and gain haste until end of turn if {R} was spent to cast this spell.': 'If {B} was spent to cast this spell, return up to one target creature card from your graveyard to the battlefield. If {R} was spent to cast this spell, creatures target player controls get +2/+0 and gain haste until end of turn.',
        'Creatures your opponents control lose flying until end of turn if {G} was spent to cast this spell, and creatures you control gain flying until end of turn if {U} was spent to cast this spell.': 'If {G} was spent to cast this spell, creatures your opponents control lose flying until end of turn. If {U} was spent to cast this spell, creatures you control gain flying until end of turn.',
        'Creatures your opponents control get -1/-0 until end of turn if {U} was spent to cast this spell, and creatures you control get +1/+0 until end of turn if {R} was spent to cast this spell.': 'If {U} was spent to cast this spell, creatures your opponents control get -1/-0 until end of turn. If {R} was spent to cast this spell, creatures you control get +1/+0 until end of turn.',
        'For each {U}{U} spent to cast it, draw a card.': 'Draw a card for each {U}{U} spent to cast it.',
        'For each {B}{B} spent to cast it, each opponent discards a card.': 'Each opponent discards a card for each {B}{B} spent to cast it.',
    }
    if text in normal:
        n = normal[text]
        got = native(n)
        return (*got, n) if got else None
    special: dict[str, tuple[str, str]] = {
        "Destroy target nonland permanent if it's a creature or if {G}{W} was spent to cast this spell.": ('destroy_if_creature', 'Destroy target nonland permanent.'),
        'You gain X life if {G} was spent to cast this spell and X life if {W} was spent to cast this spell.': ('gain_paid_colors', 'You gain X life.'),
        'Target opponent discards a card. If mana from a Treasure was spent to cast this spell, instead that player reveals their hand, you choose a nonland card from it, then that player discards that card.': ('treasure_discard', 'Target opponent discards a card.'),
        "Prevent all combat damage that would be dealt by target attacking or blocking creature this turn. If {R} was spent to cast this spell, ~ deals damage to that creature's controller equal to the creature's power.": ('prevent_then_damage', 'Prevent all combat damage that would be dealt by target attacking or blocking creature this turn.'),
        "~ deals 5 damage divided as you choose among any number of target creatures and/or planeswalkers. If {W}{U} was spent to cast this spell, until your next turn, those permanents can't attack or block and their activated abilities can't be activated.": ('divided_restrictions', '~ deals 5 damage divided as you choose among any number of target creatures and/or planeswalkers.'),
        "For each {R}{R} spent to cast it, it gets +1/+0 and gains trample and haste until end of turn.": ('pair_pump', '~ gets +1/+0 and gains trample and haste until end of turn.'),
    }
    if text in special:
        mode, proto = special[text]
        got = native(proto)
        if got is None:
            return None
        return [{'do': 'spent_mana_outcome', 'mode': mode, 'native': got[0]}], got[1], False, proto
    if text == "Target player can't play lands this turn if {R} was spent to cast this spell and can't cast creature spells this turn if {W} was spent to cast this spell.":
        land = native("Target player can't play lands this turn.")
        spells = native("Target player can't cast creature spells this turn.")
        assert land and spells
        return [*gate('R', land[0]), *gate('W', spells[0])], 'player', False, "Target player can't play lands this turn."
    if text == 'If {B} was spent to cast this spell, you may have target creature get -3/-3 until end of turn. If {G} was spent to cast this spell, you may have target creature get +3/+3 until end of turn.':
        proto = 'Target creature gets -3/-3 until end of turn. Target creature gets +3/+3 until end of turn.'
        got = native(proto)
        assert got
        es=[]
        for color, e in zip('BG', got[0], strict=True):
            es += gate(color, [{'do':'may_rest','skip':1}, e])
        return es, got[1], False, proto
    if text == "If {U} was spent to cast this spell, return up to one target creature to its owner's hand. If {B} was spent to cast this spell, target player reveals their hand, you choose a nonland card from it, then that player discards that card.":
        proto = "Return up to one target creature to its owner's hand. Target player reveals their hand. You choose a nonland card from it. That player discards that card."
        got = native(proto)
        assert got
        return [*gate('U', got[0][:1]), *gate('B', got[0][1:])], got[1], False, proto
    if text == 'Untap target creature and gain control of it until end of turn. That creature gains haste until end of turn. If {W} was spent to cast this spell, the creature gains "Whenever ~ deals combat damage, you gain that much life" until end of turn.':
        proto = 'Untap target creature. Gain control of it until end of turn. It gains haste until end of turn.'
        got = native(proto)
        assert got
        grant = {'do':'grant','who':'target','abilities':['Whenever this creature deals combat damage, you gain that much life.']}
        return [*got[0], *gate('W',[grant])], got[1], False, proto
    return None


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    got=build(body)
    return got[:3] if got else None


def definition(ability: AbilityText, ch: Characteristics) -> Definition | None:
    from dataclasses import replace

    from app.rules import scripts
    text=scripts.self_text(ability.text,ch.name)
    if ability.kind=='triggered' and text == "When you cast this spell, if {C} wasn't spent to cast it, target opponent may put a creature card from their hand onto the battlefield.":
        proto='When you cast this spell, target opponent draws a card.'
        base=scripts.define(replace(ability,text=proto),ch)
        put=native('That player may put a creature card from their hand onto the battlefield.')
        assert base and put
        base['effects']=[{**put[0][0],'who':'target'}]
        condition={'all':[{'object':'self','cast':{'total':0}}, {'not':paid('C')}]}
        base['if']=condition
        base['effects'].insert(0,{'do':'only_if','cond':condition,'skip':1})
        return base
    if ability.kind=='spell':
        lead,body='',text
    elif ability.kind=='triggered' and ', ' in text:
        first,body=text.split(', ',1)
        lead=first+', '
    else:
        return None
    got=build(body)
    if got is None or body[:1].upper()+body[1:]==got[3]:
        return None
    base=scripts.define(replace(ability,text=lead+got[3]),ch)
    if base is None:
        return None
    base['effects']=got[0]
    base['optional']=got[2]
    return base


def outcome(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import conditions, effects, values
    mode=e['mode']
    es: list[dict[str, Any]]=[]
    if mode=='gain_paid_colors':
        colors=sum(conditions.holds(plan,ctx,paid(c)) for c in 'GW')
        es=[{'do':'gain_life','who':'you','n':colors*values.evaluate(plan,ctx,{'x':1})}]
    elif mode=='destroy_if_creature':
        ids=effects._cards(plan,ctx,'target')
        if conditions.holds(plan,ctx,paid('GW')) or any(plan.ch(plan.state.cards[c]).is_creature for c in ids):
            es=e['native']
    elif mode=='treasure_discard':
        if conditions.holds(plan,ctx,{'object':'self','cast':{'from_mana':{'tag':'Treasure','n':1}}}):
            got=native('Target opponent reveals their hand. You choose a nonland card from it. That player discards that card.')
            assert got
            es=got[0]
        else:
            es=e['native']
    elif mode=='prevent_then_damage':
        ids=effects._cards(plan,ctx,'target')
        es=list(e['native'])
        if ids and conditions.holds(plan,ctx,paid('R')):
            c=plan.state.cards[ids[0]]
            ch=plan.ch(c)
            n=ch.pt[0] if ch.pt else 0
            es += [{'do':'damage','who':'player:'+c.controller,'n':max(0,n)}]
    elif mode=='divided_restrictions':
        es=list(e['native'])
        if conditions.holds(plan,ctx,paid('WU')):
            es += [{'do':'until','duration':'next_turn','n':1}, {'do':'restrict','who':'target','rules':['cant_attack_or_block','cant_activate'],'locked':True}]
    elif mode=='pair_pump':
        n=values.evaluate(plan,ctx,{'mana_pairs':{'color':'R','size':2}})
        if n:
            es=[{'do':'pump','who':'self','p':n,'t':0},{'do':'grant','who':'self','keywords':['trample','haste']}]
    i=ctx['next']
    ctx['effects'][i:i]=es
    return True

PRIMITIVES={'spent_mana_outcome':outcome}
