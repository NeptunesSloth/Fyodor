"""Exact combat and cast triggers delegate to native multi-target and base-PT effects."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

INVERSION = ('At the beginning of combat on your turn, switch the power and toughness of each '
             'of any number of target creatures until end of turn.')
WINDS = ('Whenever you cast an instant, sorcery, or Wizard spell, you may have this creature\'s '
         'base power and toughness become 4/1 or 1/4 until end of turn.')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered':
        return None
    if ability.text == INVERSION:
        native = scripts.define(replace(ability, text=(
            'At the beginning of combat on your turn, any number of target creatures each get +0/+0 until end of turn.')), ch)
        if native is None:
            return None
        return {**native, 'effects': [{'do': 'switch_pt', 'who': 'target:0'}]}
    if ability.text != WINDS:
        return None
    native = scripts.define(replace(ability, text='Whenever you cast an instant, sorcery, or Wizard spell, you may draw a card.'), ch)
    if native is None:
        return None
    options = [{'label': f'{p}/{t}', 'effects': [{'do': 'become', 'who': 'self', 'types': [], 'p': p, 't': t,
                                               'duration': 'end_of_turn'}]} for p, t in [(4, 1), (1, 4)]]
    return {**native, 'effects': [{'do': 'choose_effect', 'who': 'self', 'options': options}]}
