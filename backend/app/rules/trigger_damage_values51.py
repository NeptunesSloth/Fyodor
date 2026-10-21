"""Exact source damage predicates preserve native per-recipient event amounts."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics

PAIN = 'Whenever an opponent is dealt 3 or more damage by a single source, that player discards a card.'
TAMANOA = 'Whenever a noncreature source you control deals damage, you gain that much life.'


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    if ability.kind != 'triggered' or ability.text not in (PAIN, TAMANOA):
        return None
    if ability.text == PAIN:
        native = scripts.define(replace(ability, text='Whenever a creature deals damage to an opponent, that player discards a card.'), ch)
        if native is None:
            return None
        source = selectors.Selector(zones=('battlefield', 'stack', 'graveyard', 'hand', 'library', 'exile', 'command'))
        # A typed source selector leaves the native event player bound to the
        # recipient; subject=source intentionally binds the source controller.
        return {**native, 'cond': {'event': 'deal_damage', 'subject': 'sel', 'sel': source.key(),
                                  'to': 'opponent', 'min': 3, 'combat': None}}
    native = scripts.define(replace(ability, text='Whenever a source you control deals damage to an opponent, you gain that much life.'), ch)
    if native is None:
        return None
    source = selectors.Selector(zones=('battlefield', 'stack', 'graveyard', 'hand', 'library', 'exile', 'command'),
                                not_types=('Creature',), controller='you')
    return {**native, 'cond': {'event': 'deal_damage', 'subject': 'sel', 'sel': source.key(), 'to': 'any', 'min': 1}}
