"""Unblocked-attacker riders use native watches, exact event refs and assignment rules."""
from __future__ import annotations

import re
from typing import Any

from app.rules import selectors


def _none(who: str = 'event') -> dict[str, Any]:
    return {'do': 'restrict', 'who': who, 'rules': ['assign_none']}


def clause(text: str) -> tuple[list[dict[str, Any]], Any] | None:
    t = text.strip().rstrip('.').lower()
    if t == 'you may gain life equal to its power. if you do, it assigns no combat damage this turn':
        return ([{'do':'may_rest', 'require_life_gain': True, 'label': 'Gain life equal to that creature’s power and have it assign no combat damage this turn'},
                 {'do':'gain_life','who':'you','n':{'power':'event'}}, _none()], None)
    if t in ('it assigns no combat damage this turn and you put a cube counter on ~',
             'it assigns no combat damage this turn and you put a cube counter on this artifact'):
        return ([_none(), {'do':'add_counters','who':'self','kind':'cube','n':1}], None)
    if t == 'you may choose to have it deal damage equal to its power to a target creature. if you do, it assigns no combat damage this turn':
        return ([{'do':'may_rest', 'label': 'Have that creature deal damage and assign no combat damage this turn'}, {'do':'damage','who':'target','src':'event','n':{'power':'event'}}, _none()],
                selectors.Selector(types=('Creature',)).key())
    return None


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import watches

    m = re.fullmatch(r'(?:This turn, when|this turn, when) (?P<cond>target creature you control attacks and isn\'t blocked), (?P<clause>.+)', body.strip())
    if m:
        found = watches.parse(m['cond'], m['clause'], once=True)
        return (*found, False) if found else None
    m = re.fullmatch(r'(?:Until|until) end of turn, whenever (?P<cond>a creature you control attacks and isn\'t blocked), (?P<clause>.+)', body.strip())
    if m:
        found = watches.parse(m['cond'], m['clause'])
        return (*found, False) if found else None
    return None


def trigger(cond: dict[str, Any] | None, body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    if not cond or cond.get('event') != 'unblocked':
        return None
    t = body.strip().rstrip('.').lower()
    if cond.get('subject') == 'host' and t == ('its controller may have it deal damage equal to its power plus 2 to another target creature. '
                                               'if that player does, the attacking creature assigns no combat damage this turn'):
        return ([{'do':'may_rest','who':'ref:event.controller', 'label': 'Have that creature deal damage and assign no combat damage this turn'},
                 {'do':'damage','who':'target','src':'event','n':{'plus':[{'power':'event'},2]}}, _none()],
                [{'what':selectors.Selector(types=('Creature',),extras=('not_event',)).key()}], False)
    if cond.get('subject') == 'self' and t == ('you may exile up to two target creature cards from defending player\'s graveyard. '
                                               'if you do, you gain 1 life for each card exiled this way and ~ assigns no combat damage this turn'):
        group = {'what': selectors.Selector(types=('Creature',), zones=('graveyard',), card=True,
                                           zone_owner=selectors.DEFENDED).key(), 'min':0,'max':2}
        return ([{'do':'may_rest', 'label': 'Exile the chosen cards, gain life for them and have this creature assign no combat damage this turn'}, {'do':'exile','who':'target','as':'unblocked_exiled'},
                 {'do':'gain_life','who':'you','n':{'ref_count':'unblocked_exiled','this_way':'exiled'}}, _none('self')], [group], False)
    return None
