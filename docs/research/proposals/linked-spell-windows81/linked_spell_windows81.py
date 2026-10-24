"""Exact linked exile choices preserve their actor, timing and printed paid-cast scope."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics

RIOTER = 'Whenever ~ attacks, you may cast an Ally spell from among cards you own exiled with ~.'
AZULA_ENTER = ('When ~ enters, target opponent exiles a nontoken creature they control, '
               'then they exile a nonland card from their graveyard.')
AZULA_CAST = ('During your turn, you may cast cards exiled with ~ and you may cast them as though they had flash. '
              'Mana of any type can be spent to cast those spells.')


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import permissions, scripts, selectors

    text = scripts.self_text(ability.text, ch.name)
    if text == RIOTER:
        native = scripts.define(replace(ability, text='Whenever this creature attacks, you may cast the exiled card without paying its mana cost.'), ch)
        filt = selectors.Selector(zones=('stack',), subtypes=('Ally',), owner='you').key()
        return {**native, 'effects': [{**e, 'paid': True, 'filter': filt} if e.get('do') == 'free_cast' else e
                                    for e in native['effects']]} if native is not None else None
    if text == AZULA_ENTER:
        native = scripts.define(replace(ability, text='When this creature enters, target opponent exiles a nontoken creature they control.'), ch)
        nonland = selectors.Selector(zones=('graveyard',), card=True, not_types=('Land',)).key()
        return {**native, 'effects': [{**e, 'link': True} for e in native['effects']] +
                [{'do': 'discard', 'who': 'target', 'n': 1, 'to': 'exile', 'zone': 'graveyard',
                  'sel': nonland, 'link': True}]} if native is not None else None
    if text == AZULA_CAST:
        native = permissions.define_static('You may cast spells from among cards exiled with ~.', 'static',
                                           tuple(a.text for a in ch.abilities))
        return {**native, 'during': 'your_turn', 'flash': True, 'spend': 'type'} if native is not None else None
    return None
