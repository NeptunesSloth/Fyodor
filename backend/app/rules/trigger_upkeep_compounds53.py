"""Exact upkeep compounds retain native independent and conditional effect ordering."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

CHANCE = ('At the beginning of your upkeep, if you have 5 or less life, sacrifice this enchantment '
          'and take an extra turn after this one.')
ELDER = ('At the beginning of your upkeep, unless you sacrifice an Island, sacrifice this creature '
         'and it deals 6 damage to you.')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered':
        return None
    if ability.text == CHANCE:
        return scripts.define(replace(ability, text=CHANCE.replace(' and take', '. Take')), ch)
    if ability.text != ELDER:
        return None
    native = scripts.define(replace(ability, text=(
        'At the beginning of your upkeep, sacrifice this creature unless you sacrifice an Island.')), ch)
    if native is None:
        return None
    pay, gate, sacrifice = native['effects']
    if pay.get('do') != 'optional_payment' or gate.get('do') != 'only_if' or sacrifice.get('do') != 'sacrifice':
        return None
    return {**native, 'effects': [pay, {**gate, 'skip': 2}, sacrifice, {'do': 'damage', 'who': 'you', 'n': 6}]}
