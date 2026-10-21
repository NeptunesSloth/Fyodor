"""The created creature token remains the host while a returned Equipment gets a new identity."""
from __future__ import annotations

import re
from typing import Any


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    # Entering attached and entering before attaching are different instructions.
    # The original native return grammar handles Aura legality and Equipment failures.
    if body.endswith(' attached to that token.'):
        return scripts.parse_effects(body.replace(' attached to that token.', ' attached to that creature.'), 'event')
    m = re.fullmatch(r'(return target Equipment card from your graveyard to the battlefield), then attach it to that token\.', body, re.I)
    if m is None:
        return None
    found = scripts.parse_effects(m[1][:1].upper() + m[1][1:] + '.', None)
    if found is None or len(found[0]) != 1 or found[2] or found[0][0].get('do') != 'return_card':
        return None
    effect = found[0][0]
    if effect.get('who') != 'target' or effect.get('to') != 'battlefield':
        return None
    return ([{**effect, 'as': 'returned54'}, {'do': 'attach_to', 'src': 'ref:returned54', 'who': 'event'}], found[1], False)
