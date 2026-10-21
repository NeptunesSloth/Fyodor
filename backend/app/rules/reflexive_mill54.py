"""Native mill receipts create reflexive triggers before their targets are announced."""
from __future__ import annotations

import json
import re
from typing import Any


def parse(rest: str, base: list[dict[str, Any]], optional: bool, prev_start: int) -> dict[str, Any] | None:
    """The complete modified mill instruction must happen before its reflexive targets are chosen."""
    from app.rules import scripts
    actions = base[1:] if len(base) == 2 and base[0].get('do') == 'only_if' and base[0].get('skip') == 1 else base
    if len(actions) != 1 or actions[0].get('do') != 'mill' or actions[0].get('who') != 'you' or (optional and prev_start != 0):
        return None
    if actions[0].get('as') or actions[0].get('did') or not rest.lower().startswith('when you do, '):
        return None
    body = rest[len('when you do, '):]
    parsed = scripts.parse_effects(body[:1].upper() + body[1:], None)
    if not parsed or not parsed[0] or re.search(r'"event|"it"|"ref:', json.dumps(parsed, default=str)):
        return None
    effects, target, may = parsed
    intervening = None
    if body.lower().startswith('if '):
        if effects[0].get('do') != 'only_if' or effects[0].get('bind'):
            return None
        intervening = effects[0]['cond']
    actions[0]['did'] = 'mill54'
    ability = {'kind': 'triggered', 'trigger': 'reflexive', 'effects': effects, 'optional': may, **scripts.target_fields(target)}
    if intervening is not None:
        ability['if'] = intervening
    return {'do': 'reflexive', 'cond': {'succeeded': 'mill54'}, 'ability': ability}
