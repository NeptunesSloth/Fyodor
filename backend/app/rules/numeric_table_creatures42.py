"""Staged exact numeric tables assembled from native effects and conditions."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

_GOBLIN = ('When this creature enters from anywhere other than a graveyard or exile, '
           'if it\'s on the battlefield and you control 9 or fewer creatures named "Name Sticker" Goblin, '
           'roll a 20-sided die.')
_ROWS = ['1-6 | Add {R}{R}{R}{R}.', '7-14 | Add {R}{R}{R}{R}{R}.', '15-20 | Add {R}{R}{R}{R}{R}{R}.']


def merge_lines(ch: Any, out: dict[int, Any]) -> None:
    from app.rules import dice, scripts, selectors

    for position, ability in enumerate(ch.abilities):
        rows = ch.abilities[position + 1:position + 4]
        if ability.text == _GOBLIN + ' ' + ' '.join(_ROWS):
            rows = []
        elif ability.text != _GOBLIN or [r.text for r in rows] != _ROWS:
            continue
        native = scripts.define(replace(ability, text='When this creature enters, roll a d20.'), ch)
        if native is None or native.get('kind') != 'triggered':
            continue
        count = selectors.Selector(types=('Creature',), controller='you', extras=('name:"Name Sticker" Goblin',)).key()
        condition = {'all': [{'object': 'self', 'test': 'on_battlefield'},
                             {'not': {'object': 'self', 'cast': {'entered_from': 'graveyard'}}},
                             {'not': {'object': 'self', 'cast': {'entered_from': 'exile'}}},
                             {'value': {'count': count}, 'op': '<=', 'n': 9}]}
        effects = list(native['effects'])
        for low, high, amount in [(1, 6, 4), (7, 14, 5), (15, 20, 6)]:
            mana = scripts.parse_effects('Add ' + '{R}' * amount + '.')
            assert mana is not None
            effects += [{'do': 'only_if', 'cond': dice.condition(f'the result is {low} to {high}'), 'skip': len(mana[0])}, *mana[0]]
        out[ability.index] = {**native, 'if': condition,
                              'effects': [{'do': 'only_if', 'cond': condition, 'skip': len(effects)}, *effects]}
        for row in rows:
            out[row.index] = {'kind': 'static', 'static': 'merged', 'merged_into': ability.index}
