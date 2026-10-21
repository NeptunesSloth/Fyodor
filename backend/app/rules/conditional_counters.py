"""Conditional counters evaluate spell facts before native counter/payment instructions."""
from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from app.rules.plan import Plan


def parse(body: str) -> tuple[list[dict[str,Any]],Any,bool] | None:
    from app.rules import scripts, selectors

    t=re.sub(r'\s+',' ',body.strip()).rstrip('.')
    # A single-mode sentence also works inside the native modal parser.
    m=re.fullmatch(r'Counter (?P<sel>target creature or legendary spell) unless its controller pays (?P<cost>\{\d+\})',t)
    if m:
        base=selectors.Selector(zones=('stack',))
        sel=replace(base,either=(replace(base,types=('Creature',)).key(),replace(base,supertypes=('Legendary',)).key()))
        return ([{'do':'counter_unless','who':'target','cost':m['cost']}],sel.key(),False) if sel else None
    patterns={
        'Counter target spell if its controller is poisoned':('poison','target spell'),
        "Counter target spell if you control more creatures than that spell's controller":('creatures','target spell'),
        'Counter target spell if it was kicked':('kicked','target spell'),
        'Counter target spell if its mana value is X':('mana_value_x','target spell'),
        "Counter target spell that's the second spell cast this turn":('plain','second'),
        'Counter target spell cast from a graveyard. Draw a card':('graveyard_draw','graveyard'),
        'Counter target spell cast from a graveyard':('plain','graveyard'),
        'Counter target creature spell. If it was a legendary spell, the Ring tempts you':('legendary_ring','target creature spell'),
        'Counter target blue spell. If it was a Jace planeswalker spell, scry 2':('jace_scry','blue'),
        "Counter target spell. That spell's controller may draw a card":('controller_draw','target spell'),
        'Counter target spell unless its controller pays {1}. That player discards a card':('tax_discard','target spell'),
        'Counter target creature or planeswalker spell unless its controller pays {2}. If an opponent has eight or more cards in their graveyard, instead counter that spell, then scry 2':('graveyard_threshold','creature_pw'),
        'Counter target spell. If that spell targets a commander you control, instead counter that spell, scry 2, then draw a card':('commander_target','target spell'),
    }
    item=patterns.get(t)
    if item is None:
        return None
    test,what=item
    if what in ('second','graveyard','blue'):
        sel=selectors.Selector(zones=('stack',))
        if what=='blue':
            sel=replace(sel,colors=('U',))
        else:
            sel=replace(sel,extras=(*sel.extras,'counter_cast:'+what))
        what=sel.key()
    elif what=='creature_pw':
        sel=replace(selectors.Selector(zones=('stack',)),types=('Creature','Planeswalker'))
        if sel is None:
            return None
        what=sel.key()
    else:
        what=scripts.SELECTORS[what]
    return [{'do':'conditional_counter','who':'target','test':test}],what,False


def cast_filter(plan: Plan,card: Any,kind: str) -> bool:
    from app.rules import history

    oid=plan.oid(card)
    if kind=='graveyard':
        rec=plan.rules.payments.get(oid)
        return rec is not None and rec.cast_from=='graveyard'
    notes=history.log_for(plan).casts
    return len(notes)>=2 and notes[1].object_id==oid


def run(plan: Plan,ctx: dict[str,Any],e: dict[str,Any]) -> bool:
    from app.rules import effects, scripts

    ids=effects._stack_targets(plan,ctx,e)
    if len(ids)!=1:
        return True
    card=plan.state.cards[ids[0]]
    ch=plan.ch(card)
    pid=card.controller
    you=ctx['controller']
    rec=plan.rules.payments.get(plan.oid(card))
    test=e['test']
    counter={'do':'counter','who':'target'}
    tail: list[dict[str,Any]]=[]
    if test=='poison' and plan.state.players[pid].resources.get('poison',0)<=0:
        return True
    if test=='creatures':
        def count(player: str) -> int:
            return sum(c.zone.endswith(':battlefield') and c.controller==player and 'Creature' in plan.ch(c).types for c in plan.state.cards.values())
        if count(you)<=count(pid):
            return True
    if test == 'mana_value_x':
        from app.rules import stack_interaction, values
        if stack_interaction.mana_value(card, ch) != values.evaluate(plan, ctx, {"x": 1}):
            return True
    if test=='kicked' and (rec is None or rec.kicked<=0):
        return True
    if test=='graveyard_draw':
        tail=[{'do':'draw','who':'you','n':1}]
    if test=='legendary_ring' and 'Legendary' in ch.supertypes:
        native=scripts.parse_effects('The Ring tempts you.')
        assert native is not None
        tail=native[0]
    if test=='jace_scry' and 'Planeswalker' in ch.types and 'Jace' in ch.subtypes:
        tail=[{'do':'scry','who':'you','n':2}]
    if test=='controller_draw':
        tail=[{'do':'draw','who':'player:'+pid,'n':1,'may':True}]
    if test=='tax_discard':
        counter={'do':'counter_unless','who':'target','cost':'{1}'}
        tail=[{'do':'discard','who':'player:'+pid,'n':1}]
    if test=='graveyard_threshold':
        qualifies=any(p!=you and len(plan.state.zones.get(p+':graveyard',[]))>=8 for p in plan.state.players)
        if qualifies:
            tail=[{'do':'scry','who':'you','n':2}]
        else:
            counter={'do':'counter_unless','who':'target','cost':'{2}'}
    if test=='commander_target':
        entry=plan.rules.stack.get(card.id)
        targets=entry.targets if entry is not None else []
        qualifies=any((target:=plan.state.cards.get(t.id)) is not None and target.commander_key is not None
                      and target.controller==you and plan.oid(target)==t.object_id for t in targets)
        if qualifies:
            tail=[{'do':'scry','who':'you','n':2},{'do':'draw','who':'you','n':1}]
    i=ctx['next']
    ctx['effects'][i:i]=[counter,*tail]
    return True
