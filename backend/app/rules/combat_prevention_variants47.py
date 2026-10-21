"""Unregistered exact prevention sentences for Dromoka's Command and Winds."""
from __future__ import annotations

from typing import Any

COMMAND = 'Prevent all damage target instant or sorcery spell would deal this turn.'
WIND_BASE = 'Prevent all combat damage that would be dealt this turn.'
WIND_ALT = 'If you control a creature with power 4 or greater, instead prevent all combat damage that would be dealt this turn by creatures your opponents control.'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import selectors

    text = body.strip()
    if text == COMMAND:
        return ([{'do': 'source_shield', 'props': {}, 'once': False, 'src': 'target', 'to': None}],
                'instant_or_sorcery_spell', False)
    if text != WIND_BASE + ' ' + WIND_ALT:
        return None
    four = selectors.Selector(types=('Creature',), controller='you', compare=(('power', '>=', 4),)).key()
    opponents = selectors.Selector(types=('Creature',), controller='opponent').key()
    cond = {'value': {'count': four}, 'op': '>=', 'n': 1}
    return ([{'do': 'only_if', 'cond': {'not': cond}, 'skip': 1, 'bind': 'winds47'},
             {'do': 'prevent_all', 'scope': {'combat': True, 'any_target': True}},
             {'do': 'only_if', 'cond': {'flag': 'winds47', 'negate': True}, 'skip': 1},
             {'do': 'prevent_all', 'scope': {'combat': True, 'any_target': True, 'by_objects': opponents}}],
            None, False)
