"""Exact-target delayed effects using native event, step and replacement continuations."""
from __future__ import annotations

import re
from typing import Any

Parsed = tuple[list[dict[str, Any]], Any, bool]


def _watch(cond: dict[str, Any], who: str | None, effects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from app.rules import delayed

    text = {'dealt_damage':'that creature is dealt damage', 'deal_damage':'that creature deals damage',
            'you_attack':'you attack'}[cond['event']]
    wrapped = delayed.wrap_when(effects, {'kind':'watch','cond':cond,'text':text,**({'bound':True} if who else {})},
                                 who=who,this_turn=True)
    wrapped[0]['once'] = False
    return wrapped


def _event(kind: str, who: str, effects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from app.rules import delayed

    return delayed.wrap_when(effects,{'kind':'event','event':kind},who=who,this_turn=True)


def parse(body: str) -> Parsed | None:
    from app.rules import delayed, language, selectors

    body=body.strip()
    m=re.fullmatch(r"(?P<target>[Uu]p to one target creature you control|[Tt]arget creature you control) can't be blocked this turn\. Whenever that creature deals (?P<combat>combat )?damage this turn, (?P<rest>.+)",body)
    if m:
        group=language.target_group(m['target'].lower())
        rest=m['rest']
        deferred: list[dict[str, Any]] | None = None
        if rest=="return it to its owner's hand.":
            deferred=[{'do':'bounce','who':'event'}]
        elif rest=="you may exile it. If you do, return it to the battlefield under its owner's control.":
            deferred=[{'do':'may_rest','skip':2,'label':'Exile and return that creature'},
                      {'do':'exile','who':'event','as':'bound_exile'},
                      {'do':'return_card','who':'ref:bound_exile','to':'battlefield','under':'owner','tapped':False}]
        if group is not None and deferred is not None:
            cond={'event':'deal_damage','subject':'sel','sel':selectors.Selector(types=('Creature',)).key(),
                  'to':'any','combat':True if m['combat'] else None}
            return ([{'do':'restrict','who':'target','rules':['cant_be_blocked']},
                     *_watch(cond,'target',deferred)],[group],False)
    if body=="Choose target creature an opponent controls. Whenever you attack this turn, ~ deals damage equal to the number of attacking creatures to that creature.":
        group=language.target_group('target creature an opponent controls')
        if group is not None:
            amount={'count':selectors.Selector(types=('Creature',),attacking=True).key()}
            return ([{'do':'choose_targets','who':'target'},
                     *_watch({'event':'you_attack','subject':'player','player':'you'},None,
                             [{'do':'damage','who':'target','n':amount}])],[group],False)
    if body=='Choose target creature. Whenever that creature is dealt damage this turn, it deals that much damage to each other creature and each player.':
        group=language.target_group('target creature')
        if group is not None:
            cond={'event':'dealt_damage','subject':'sel','sel':selectors.Selector(types=('Creature',)).key()}
            key=selectors.Selector(types=('Creature',)).key()
            damage: list[dict[str, Any]] = [{'do':'damage','who':f'except:event|{key}','src':'event','n':{'event_amount':1},'with_next':True},
                    {'do':'damage','who':'each_player','src':'event','n':{'event_amount':1}}]
            return ([{'do':'choose_targets','who':'target'},*_watch(cond,'target',damage)],[group],False)
    if body=='Choose target Wall creature. Whenever that creature is dealt damage by an attacking creature this turn, you gain that much life.':
        group=language.target_group('target Wall creature')
        if group is not None:
            cond={'event':'dealt_damage','subject':'sel','sel':selectors.Selector(types=('Creature',)).key(),
                  'damage_source':selectors.Selector(types=('Creature',),attacking=True).key()}
            return ([{'do':'choose_targets','who':'target'},
                     *_watch(cond,'target',[{'do':'gain_life','who':'you','n':{'event_amount':1}}])],[group],False)
    if body=="Choose target creature. When that creature dies this turn, return a creature card from its owner's graveyard to the battlefield under the control of that creature's owner.":
        group=language.target_group('target creature')
        if group is not None:
            key=selectors.Selector(card=True,types=('Creature',),zones=('graveyard',)).key()
            effect={'do':'return_choice','who':f'graveyard_of:ref:event.owner|{key}',
                    'n':1,'upto':False,'random':False,'label':'creature card','to':'battlefield',
                    'tapped':False,'under':'ref:event.owner'}
            return ([{'do':'choose_targets','who':'target'},*_event('die','target',[effect])],[group],False)
    if body=='Choose target creature an opponent controls. When that creature dies this turn, you gain 3 life. Target creature you control fights that creature.':
        first=language.target_group('target creature an opponent controls')
        second=language.target_group('target creature you control')
        if first is not None and second is not None:
            return ([{'do':'choose_targets','who':'target:0'},
                     *_event('die','target:0',[{'do':'gain_life','who':'you','n':3}]),
                     {'do':'fight','who':'target:1','with':'target:0'}],[first,second],False)
    if body=="Target creature you control can't be blocked this turn. Destroy it and ~ at end of combat.":
        group=language.target_group('target creature you control')
        if group is not None:
            # The native delayed binder freezes both members of this exact-object union.
            return ([{'do':'restrict','who':'target','rules':['cant_be_blocked']},
                     *delayed.wrap_when([{'do':'destroy','who':'union:target+self'}],delayed.END_OF_COMBAT)],
                    [group],False)
    if body=='Choose target attacking or blocking creature whose controller controls an Island. ~ deals 2 damage to that creature at end of combat.':
        group=language.target_group('target attacking or blocking creature whose controller controls an Island')
        if group is not None:
            return ([{'do':'choose_targets','who':'target'},
                     *delayed.wrap_when([{'do':'damage','who':'target','n':2}],delayed.END_OF_COMBAT)],[group],False)
    if body=="Target creature you control with toughness 2 or less gets +1/+1 and gains flying until end of turn. When ~ leaves the battlefield this turn, sacrifice that creature. When the creature leaves the battlefield this turn, sacrifice ~.":
        group=language.target_group('target creature you control with toughness 2 or less')
        if group is not None:
            return ([{'do':'pump','who':'target','p':1,'t':1},
                     {'do':'grant','who':'target','keywords':['flying']},
                     *_event('leave','self',[{'do':'sacrifice','who':'target'}]),
                     *_event('leave','target',[{'do':'sacrifice','who':'self'}])],[group],False)
    return None
