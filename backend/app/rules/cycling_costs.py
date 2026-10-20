"""CR 702.29: cycling costs and typecycling's search predicate."""
from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

_MANA = r'(?:\{[^}]+\})+'
MANA_CYCLING = re.compile(rf'^(?P<kind>(?:(?:basic|artifact) )?[a-z]+)?cycling (?P<cost>{_MANA})$', re.I)
_NONMANA = re.compile(r'^cycling\s*[—-]\s*(?P<cost>.+)$', re.I)


def mana_only(cost: str) -> bool:
    return re.fullmatch(_MANA, cost) is not None


def search_selector(kind: str) -> str | None:
    from app.rules import selectors

    for phrase in dict.fromkeys((kind + ' card', kind.capitalize() + ' card')):
        sel = selectors.parse(phrase)
        if sel is not None and sel.card and sel.player is None and not sel.ability:
            return replace(sel, zones=('library',), zone_owner='you').key()
    return None


def parts(text: str) -> list[tuple[str, str]]:
    from app.rules import costs, mana, oracle

    text = oracle.strip_reminders(text).strip().rstrip('.')
    if m := _NONMANA.fullmatch(text):
        cost = costs.parse_ability_cost(m['cost'])
        if cost.unsupported or not cost.components or cost.from_hand or cost.sacrifice_self:
            return []
        return [('', m['cost'])]
    out = []
    for piece in re.split(r',\s*', text):
        m = MANA_CYCLING.fullmatch(piece)
        if m is None or mana.parse_cost(m['cost']).unsupported:
            return []
        kind = (m['kind'] or '').strip()
        if kind and search_selector(kind) is None:
            return []
        out.append((kind, m['cost']))
    return out


def effects(kind: str) -> list[dict[str, Any]]:
    if not kind:
        return [{'do': 'draw', 'who': 'you', 'n': 1}]
    selector = search_selector(kind)
    assert selector is not None
    return [{'do': 'search', 'who': 'you', 'sel': selector, 'max': 1, 'to': 'hand', 'reveal': True}]
