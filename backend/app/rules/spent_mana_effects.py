"""Native effect compositions for quantities based on actual spell payments."""
from __future__ import annotations

import copy
import re
from typing import Any


def normalize(body: str) -> str | None:
    changed=re.sub(r'(?P<head>[Ii]f \w+ or more mana was spent to cast that spell, sacrifice ~ and) (?:it|~) deals that much damage to each opponent',
                   r'\g<head> ~ deals X damage to each opponent, where X is the amount of mana spent to cast that spell',body)
    changed=re.sub(r'[Yy]ou may cast (?P<sel>[A-Za-z][A-Za-z\x27 -]*?) spells from among them this turn\.',
                   r'Until end of turn, you may cast \g<sel> spells from among them.',changed)
    return changed if changed!=body else None


def _controller_draws(value: Any) -> Any:
    if isinstance(value,list):
        return [_controller_draws(x) for x in value]
    if not isinstance(value,dict):
        return value
    out={k:_controller_draws(v) for k,v in value.items()}
    if out.get('this_way')=='drawn':
        out['players']='you'
    return out


def parse(body: str) -> tuple[list[dict[str,Any]],Any,bool] | None:
    from app.rules import scripts, values

    t=body.strip().rstrip('.')
    if 'If you draw one or more cards this way' in t:
        rewritten=t.replace('If you draw one or more cards this way','If at least one card was drawn this way')+'.'
        if (found:=scripts.parse_effects(rewritten)) is not None:
            return _controller_draws(found[0]),found[1],found[2]
    m=re.fullmatch(r'[Gg]ain control of (?P<target>target creature) if (?P<condition>its (?:power|toughness|mana value) is less than or equal to the number of colors of mana spent to cast (?:this spell|~))',t)
    if m is not None:
        # The first synthetic clause supplies the native target binding only.
        found=scripts.parse_effects(f"Gain control of {m['target']}. If {m['condition']}, gain control of it.")
        if found is not None:
            return found[0][1:],found[1],found[2]
    m=re.fullmatch(r'(?P<first>[Cc]reate .+? creature token .+?)\. Then for each opponent with (?P<n>\w+) or more (?P<kind>[a-z]+) counters, you create another one of those tokens',t)
    if m is not None:
        found=scripts.parse_effects(m['first']+'.')
        n=int(m['n']) if m['n'].isdigit() else values.NUMBERS.get(m['n'])
        if found is not None and len(found[0])==1 and found[0][0].get('do')=='create_token' and n is not None:
            extra=copy.deepcopy(found[0][0])
            extra['n']={'players_with_counters':{'who':'opponents','kind':m['kind'],'at_least':n}}
            return [*found[0],extra],found[1],found[2]
    return None
