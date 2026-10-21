"""A native maximum common-type count supplies the exact intervening condition."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = ('When this creature enters, if you control three or more creatures that share a creature type, '
        'put a +1/+1 counter on this creature, then scry 1.')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    if ability.kind != 'triggered' or ability.text != TEXT:
        return None
    native = scripts.define(replace(ability, text=TEXT.replace(
        'if you control three or more creatures that share a creature type, ', '')), ch)
    if native is None:
        return None
    condition = {'value': {'shared_type': True, 'of': selectors.Selector(types=('Creature',), controller='you').key()},
                 'op': '>=', 'n': 3}
    return {**native, 'if': condition, 'effects': [
        {'do': 'only_if', 'cond': condition, 'skip': len(native['effects'])}, *native['effects']]}
