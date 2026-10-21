"""Battle of Wits checks the native library count at trigger time and resolution."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = ('At the beginning of your upkeep, if you have 200 or more cards in your library, '
        'you win the game.')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or ability.text != TEXT:
        return None
    native = scripts.define(replace(ability, text='At the beginning of your upkeep, you win the game.'), ch)
    if native is None:
        return None
    condition = {'value': {'library': 'you'}, 'op': '>=', 'n': 200}
    return {**native, 'if': condition, 'effects': [{'do': 'only_if', 'cond': condition, 'skip': 1}, *native['effects']]}
