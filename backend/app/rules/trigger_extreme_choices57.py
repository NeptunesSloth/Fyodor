"""Untargeted least-stat upkeep choices use full native characteristics at resolution."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

POWER = ('At the beginning of your upkeep, destroy the creature with the least power. It can\'t be regenerated. '
         'If two or more creatures are tied for least power, you choose one of them.')
TOUGHNESS = ('At the beginning of your upkeep, this artifact deals 2 damage to the creature with the least toughness. '
             'If two or more creatures are tied for least toughness, you choose one of them.')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    if ability.kind != 'triggered' or ability.text not in (POWER, TOUGHNESS):
        return None
    native = scripts.define(replace(ability, text='At the beginning of your upkeep, you gain 1 life.'), ch)
    if native is None:
        return None
    all_creatures = selectors.Selector(types=('Creature',)).key()
    effects: list[dict[str, Any]]
    if ability.text == POWER:
        sel = selectors.Selector(types=('Creature',), without_keywords=('indestructible',),
                                 extras=('ext:least:power:' + all_creatures,))
        effects = [{'do': 'destroy', 'who': 'ref:least'}, {'do': 'no_regen'}]
    else:
        sel = selectors.Selector(types=('Creature',), extras=('ext:least:toughness:self',))
        effects = [{'do': 'damage', 'who': 'ref:least', 'n': 2}]
    choice = {'do': 'player_chooses', 'who': 'you', 'any': True, 'sel': sel.key(), 'n': 1,
              'label': 'creature with the least ' + ('power' if ability.text == POWER else 'toughness'), 'as': 'least'}
    return {**native, 'effects': [choice, *effects]}
