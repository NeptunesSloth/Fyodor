"""Native exact-object exile and suspend-grant follow-through recipes."""
from __future__ import annotations

import re
from typing import Any


def _suspend(who: str, n: int | None = None, **flags: Any) -> dict[str, Any]:
    return {'do':'suspend_found', 'who':who, 'n':0 if n is None else n, **flags}


def _base_parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import pay_objects
    text=body.strip()
    text=text[:1].upper()+text[1:]
    if text=="Put four time counters on the exiled card. If it doesn't have suspend, it gains suspend." and pay_objects.activation_exiled():
        return ([_suspend('cost:exiled',4)],None,False)
    if text=="Exile the top five cards of your library. For each nonland card exiled this way, put a number of time counters on that card equal to its mana value. If it doesn't have suspend, it gains suspend.":
        return ([{'do':'exile_top','player':'you','n':5,'as':'suspend_exiled'},
                 _suspend('ref:suspend_exiled',per_card_mv=True,nonland=True)],None,False)
    if text=="Exile the top three cards of your library. You may play those cards until end of turn. Put four time counters on each of those cards that has suspend.":
        return ([{'do':'exile_top','player':'you','n':3,'as':'suspend_exiled'},
                 {'do':'grant_play','who':'ref:suspend_exiled','play':True,'cast':True,'until':'end_of_turn'},
                 _suspend('ref:suspend_exiled',4,only_existing=True)],None,False)
    return None


def _base_definition(text: str) -> dict[str, Any] | None:
    from app.rules import events
    text=re.sub(r'^[^\n—]+ — (?=When(?:ever)?|At )','',text)
    if text=="Whenever you cast your second spell each turn, copy it, then exile the spell you cast with four time counters on it. If it doesn't have suspend, it gains suspend.":
        cond=events.parse_condition('you cast your second spell each turn')
        assert cond is not None
        return {'kind':'triggered','trigger':'event','cond':cond,'optional':False,'target':None,
                'effects':[{'do':'copy_spell','who':'event_spell','first':True},
                           {'do':'exile','who':'event_spell','as':'suspend_exiled'},
                           _suspend('ref:suspend_exiled',4)]}
    return None


def _hand_sequence(who: str, binding: str, *, nonland: bool = False, grant: bool = True) -> list[dict[str, Any]]:
    return [
        {'do':'optional_payment','who':who,'cost':f"Exile a {'nonland ' if nonland else ''}card from your hand",'bind':binding},
        {'do':'only_if','cond':{'succeeded':binding},'skip':1},
        _suspend(f'ref:{binding}',per_card_mv=True,by=who,grant=grant),
    ]



def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import selectors
    text = body.strip()
    text = text[:1].upper() + text[1:]
    if text == "Draw two cards, then you may exile a nonland card from your hand with a number of time counters on it equal to its mana value. Then target opponent does the same. Cards exiled this way that don't have suspend gain suspend.":
        opponent = selectors.parse('opponent')
        assert opponent is not None
        return ([{'do':'draw','who':'you','n':2},
                 *_hand_sequence('you','suspend_first',nonland=True,grant=False),
                 {'do':'draw','who':'target','n':2},
                 *_hand_sequence('target','suspend_second',nonland=True,grant=False),
                 {'do':'suspend_mark','who':'ref:suspend_first'},
                 {'do':'suspend_mark','who':'ref:suspend_second'}], opponent.key(), False)
    return _base_parse(body)



def definition(text: str) -> dict[str, Any] | None:
    from app.rules import events, scripts, selectors
    text = re.sub(r'^[^\n—]+ — (?=When(?:ever)?|At )','',text)
    if text == "Whenever ~ deals combat damage to a player, you may exile a card from your hand with a number of time counters on it equal to its mana value. If it doesn't have suspend, it gains suspend.":
        cond = events.parse_condition('~ deals combat damage to a player')
        assert cond is not None
        return {'kind':'triggered','trigger':'event','cond':cond,'optional':False,'target':None,
                'effects':_hand_sequence('you','suspend_hand')}
    if text == "When you cast this spell from anywhere other than exile, exile it with three time counters on it. It gains suspend. Then investigate.":
        investigate = scripts.parse_effects('Investigate.')
        assert investigate is not None
        return {'kind':'triggered','trigger':'cast_self','optional':False,'target':None,
                'if':{'object':'self','cast':{'from':'!exile'}},
                'effects':[{'do':'exile','who':'event_spell','as':'suspend_exiled'},
                           _suspend('ref:suspend_exiled',3),*investigate[0]]}
    if text == "When ~ dies, you may exile it and put three time counters on it. If you do, exile up to one target creature and put three time counters on it. Each card exiled this way that doesn't have suspend gains suspend.":
        target = selectors.parse('creature')
        assert target is not None
        return {'kind':'triggered','trigger':'dies_self','optional':False,
                'target':None,'targets':[{'what':target.key(),'min':0,'max':1}],
                'effects':[{'do':'suspend_departed_source'}]}
    if text == "At the beginning of each player's upkeep, if this card is suspended, that player may sacrifice a permanent of their choice. If the player does, put two time counters on this card.":
        return {'kind':'triggered','trigger':'step:upkeep:each','exiled_step':True,
                'if':{'object':'self','test':'suspended'},'optional':False,'target':None,
                'effects':[{'do':'optional_payment','who':'event_player','cost':'Sacrifice a permanent','bind':'suspend_curse_paid'},
                           {'do':'only_if','cond':{'succeeded':'suspend_curse_paid'},'skip':1},
                           {'do':'suspend_source_counters','n':2}]}
    return _base_definition(text)


def departed_source(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import context
    from app.rules.plan import decide
    cards = [cid for cid in context.objects(plan,ctx,context.EVENT_NEW)
             if cid == ctx.get('source_card') and plan.state.cards[cid].zone.endswith(':graveyard')]
    if not cards:
        return True
    context.bind_objects(plan,ctx,'suspend_departed',cards)
    decide(plan,player=ctx['controller'],kind='choose_one',prompt='Exile Sinister Concierge with three time counters?',
           options=[DecisionOption(id='yes',label='Exile it'),DecisionOption(id='no',label="Don't exile it")],
           resume={'step':'suspend_departed_source','ctx':ctx,'e':e})
    return False


def resume_departed(plan: Any, decision: Any, chosen: list[str]) -> None:
    from app.rules import context, effects
    ctx = decision.resume['ctx']
    cards = context.objects(plan,ctx,'suspend_departed')
    if chosen == ['yes'] and cards and plan.state.cards[cards[0]].zone.endswith(':graveyard'):
        tail = [{'do':'exile','who':'ref:suspend_departed','as':'suspend_source_exiled'},
                _suspend('ref:suspend_source_exiled',3,grant=False),
                {'do':'exile','who':'target:0','as':'suspend_target_exiled'},
                _suspend('ref:suspend_target_exiled',3,grant=False),
                {'do':'suspend_mark','who':'ref:suspend_source_exiled'},
                {'do':'suspend_mark','who':'ref:suspend_target_exiled'}]
        at = int(ctx.get('next') or 0)
        ctx['effects'][at:at] = tail
    effects.continue_effects(plan,ctx)


def source_counters(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, suspend_grants
    card = plan.state.cards.get(ctx.get('source_card') or '')
    if card is None or not card.zone.endswith(':exile') or plan.oid(card) != ctx.get('source_object'):
        return True
    context.bind_objects(plan,ctx,'suspend_source', [card.id])
    return suspend_grants.suspend_found(plan,ctx,{**e,'who':'ref:suspend_source','grant':False})


PRIMITIVES = {'suspend_departed_source':departed_source,'suspend_source_counters':source_counters}
RESUME = {'suspend_departed_source':resume_departed}
