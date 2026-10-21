"""A completed single roll supplies an immutable quantity to its reflexive ability (603.12)."""
from __future__ import annotations

import json
import re
from typing import Any


def parse(body: str, it: str | None, event_player: bool) -> tuple[list[dict[str, Any]], Any, bool] | None:
    m = re.fullmatch(r'(?P<roll>Roll [^.]+)\. When you do, (?P<body>.+), where X is the result\.', body, re.IGNORECASE)
    if m is None:
        return None
    from app.rules import scripts

    lead = scripts.parse_effects(m['roll'] + '.', it, event_player=event_player)
    if lead is None or lead[1] is not None or lead[2] or len(lead[0]) != 1:
        return None
    roll = lead[0][0]
    if roll.get('do') != 'roll' or roll.get('count') != 1 or roll.get('choose'):
        return None
    text = m['body'][:1].upper() + m['body'][1:] + '.'
    found = scripts.parse_effects(text, 'self' if it == 'self' else None)
    if found is None or not found[0]:
        return None
    effects, target, optional = found
    raw = json.dumps([effects, target])
    if re.search(r'"(?:die|dice|event_amount|event_player|that_player|event|it)"', raw):
        return None  # Only the explicit roll quantity crosses this resolution boundary.
    if not re.search(r'"x"|"X"|\bX\b', raw):
        return None
    ability = {'kind': 'triggered', 'trigger': 'reflexive', 'effects': scripts._x_to_event(effects),
               'optional': optional, **scripts.target_fields(target), 'x_event': True}
    return [roll, {'do': 'reflexive', 'cond': {}, 'roll_result': True, 'ability': ability}], None, False
