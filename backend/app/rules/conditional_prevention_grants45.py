"""Exact compound statics using native replacement and layer-6 consumers."""
from __future__ import annotations

from typing import Any

WOOLLY = 'As long as ~ has an ice counter on it, prevent all combat damage it would deal and it has defender.'
ARMAMENT = "Enchanted creature has double strike as long as it's an enchantment. Otherwise, prevent all damage that would be dealt by enchanted creature."
REMINDER = ' (A creature with double strike deals both first-strike and regular combat damage.)'


def _woolly() -> dict[str, Any]:
    from app.rules import statics

    condition = {'static': 'self_counter', 'counter': 'ice', 'op': '>=', 'n': 1}
    return {'kind': 'static', 'static': 'replace', 'event': 'damage',
            'static_if': [condition], 'match': {'combat': True, 'source': {'self': True}},
            'op': {'do': 'prevent_all', 'prevention': True}, 'effects': [],
            'also': [statics.parse('As long as ~ has an ice counter on it, it has defender.')]}


def _armament() -> dict[str, Any]:
    from app.rules import selectors, statics

    return {'kind': 'static', 'static': 'replace', 'event': 'damage',
            'match': {'source': {'attached': True, 'sel': selectors.Selector(not_types=('Enchantment',)).key()}},
            'op': {'do': 'prevent_all', 'prevention': True}, 'effects': [],
            'also': [statics.parse("Enchanted creature has double strike as long as it's an enchantment.")]}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'static':
        return None
    text = scripts.self_text(ability.text, ch.name).replace('this creature', '~').replace('This creature', '~')
    if text == WOOLLY:
        return _woolly()
    if text in (ARMAMENT, ARMAMENT + REMINDER):
        return _armament()
    return None


def supported(definition: dict[str, Any]) -> bool:
    return definition in (_woolly(), _armament())


def layer6_grant(definition: dict[str, Any]) -> dict[str, Any] | None:
    if not supported(definition):
        return None
    grants = definition.get('also')
    return grants[0] if isinstance(grants, list) and len(grants) == 1 and isinstance(grants[0], dict) else None
