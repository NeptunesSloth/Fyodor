"""Payment-conditional spell riders composed from native target/effect primitives."""
from __future__ import annotations

import copy
import re
from typing import Any


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import conditions, scripts

    t = body.strip().rstrip('.')
    m = re.fullmatch(r'(?P<first>Return target card from your graveyard to your hand\. Put up to one other target card from your graveyard on top of your library\. Exile ~\.) If (?P<cond>at least three green mana was spent to cast this spell), instead return those cards to your hand and exile ~', t)
    if m is not None:
        base = scripts.parse_effects(m['first'])
        cond = conditions.parse(m['cond'], objects=True)
        if base is not None and cond is not None:
            first, second, last = base[0]
            alternate = copy.deepcopy(first)
            alternate['who'] = second['who']
            return [first, {'do': 'only_if', 'cond': cond, 'skip': 1}, alternate,
                    {'do': 'only_if', 'cond': {'not': cond}, 'skip': 1}, second, last], base[1], False
    m = re.fullmatch(r'(?P<first>Put a \+1/\+1 counter on target creature you control, then it fights target creature you don\x27t control\.) If (?P<cond>at least three green mana was spent to cast this spell), the creature you control gains indestructible until end of turn', t)
    if m is not None:
        base = scripts.parse_effects(m['first'])
        cond = conditions.parse(m['cond'], objects=True)
        if base is not None and cond is not None:
            return [*base[0], {'do': 'only_if', 'cond': cond, 'skip': 1},
                    {'do': 'grant', 'who': 'target:0', 'keywords': ['indestructible']}], base[1], False
    if t == 'You may choose a creature card in your graveyard. If you do, return it to the battlefield with an additional +1/+1 counter on it':
        base = scripts.parse_effects('You may return a creature card from your graveyard to the battlefield with an additional +1/+1 counter on it.')
        if base is not None:
            effects = copy.deepcopy(base[0])
            effects[0]['upto'] = True
            return effects, base[1], False
    m = re.fullmatch(r'(?P<first>~ deals 7 damage divided as you choose among one, two, or three targets\.) If (?P<cond>at least seven red mana was spent to cast this spell), instead ~ deals 7 damage to each of those permanents and/or players', t)
    if m is not None:
        base = scripts.parse_effects(m['first'])
        cond = conditions.parse(m['cond'], objects=True)
        if base is not None and cond is not None:
            alternate = copy.deepcopy(base[0][0])
            alternate['n'] = 7
            return [{'do': 'only_if', 'cond': cond, 'skip': 1}, alternate,
                    {'do': 'only_if', 'cond': {'not': cond}, 'skip': len(base[0])}, *base[0]], base[1], False
    return None
