"""The greatest-power graveyard return remains an untargeted native choice."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = ('When this creature enters, return to your hand the creature card in your graveyard with the greatest power. '
        'If two or more cards are tied for greatest power, you choose one of them.')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    if ability.kind != 'triggered' or ability.text != TEXT:
        return None
    native = scripts.define(replace(ability, text='When this creature enters, you gain 1 life.'), ch)
    returned = scripts.parse_effects('Return target creature card from your graveyard to your hand.')
    if native is None or returned is None:
        return None
    sel = selectors.Selector(types=('Creature',), zones=('graveyard',), zone_owner='you', card=True,
                             extras=('ext:greatest:power:self',))
    choice = {'do': 'player_chooses', 'who': 'you', 'any': True, 'sel': sel.key(), 'n': 1,
              'label': 'creature card with greatest power in your graveyard', 'as': 'greatest'}
    return {**native, 'effects': [choice, {**returned[0][0], 'who': 'ref:greatest|' + sel.key()}]}
