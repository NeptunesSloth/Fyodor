"""Counter removal results, paid quantities, and source-counter thresholds."""
from __future__ import annotations

from typing import Any


def parse(body: str) -> tuple[list[dict[str,Any]],Any,bool] | None:
    from app.rules import scripts

    text=body.strip().rstrip('.')
    text=text[:1].upper()+text[1:]
    if text=='Remove a hope counter from ~. If you do, draw a card. Then if ~ has no hope counters on it, sacrifice it and you gain 4 life':
        return ([{'do':'remove_counters','who':'self','kind':'hope','n':1,'bind':'hope_removed'},
                 {'do':'only_if','cond':{'value':{'ref_amount':'hope_removed'},'op':'>','n':0},'skip':1},
                 {'do':'draw','who':'you','n':1},
                 {'do':'only_if','cond':{'value':{'counters':'hope','on':'self'},'op':'==','n':0},'skip':2},
                 {'do':'sacrifice','who':'self'},{'do':'gain_life','who':'you','n':4}],None,False)
    if text=='Counter that spell and put a depletion counter on ~. If there are three or more depletion counters on ~, sacrifice it':
        return scripts.parse_effects('Counter that spell. Put a depletion counter on ~. If ~ has three or more depletion counters on it, sacrifice it.')
    if text=='Draw a card for each verse counter on ~. If it had seven or more verse counters on it, take an extra turn after this one':
        return scripts.parse_effects('Draw a card for each verse counter on ~. If ~ has seven or more verse counters on it, take an extra turn after this one.')
    if text=='For each counter paid, ~ gets +2/+0 until end of turn':
        return ([{'do':'pump','who':'self','p':{'times':[2,{'x':1}]},'t':0}],None,False)
    if text=="Return ~ to its owner's hand unless you remove two oil counters from it":
        return scripts.parse_effects("You may remove two oil counters from ~. If you don't, return ~ to its owner's hand.")
    return None
