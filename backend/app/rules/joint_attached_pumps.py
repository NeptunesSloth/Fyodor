"""CR 613.4c sibling statics for a source and its enchanted creature."""
from __future__ import annotations

import re
from typing import Any


def definition(text: str) -> dict[str, Any] | None:
    from app.rules import statics

    m = re.fullmatch(r'(?:~|[Tt]his creature) and enchanted creature each get (?P<predicate>.+)\.', text.strip())
    if m is None:
        return None
    # Each independent "for each" term is additive: an Aura creature belongs to both sets.
    pieces = re.split(r' and (?=[+]\d+/[+]\d+ for each )', m['predicate'])
    siblings = [statics.parse(f'{subject} gets {piece}.') for subject in ('~', 'Enchanted creature') for piece in pieces]
    if any(d is None or d.get('also') for d in siblings):
        return None
    first = dict(siblings[0] or {})
    first['also'] = siblings[1:]
    return first
