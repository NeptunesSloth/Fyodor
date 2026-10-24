"""Actual stack spells gain native abilities with ordinary object and duration lifetimes."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics

GALEA_QUOTE = 'When this Equipment enters, attach it to target creature you control.'
GALEA = ('You may cast Aura and Equipment spells from the top of your library. '
         'When you cast an Equipment spell this way, it gains "' + GALEA_QUOTE.replace('this Equipment', '~') + '"')
ELF = 'Whenever you cast an Elf spell, it gains haste until end of turn and you draw two cards.'


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import permissions, scripts, selectors

    text = scripts.self_text(ability.text, ch.name)
    choices = {
        'Whenever you cast an artifact creature spell, it gains sunburst.': ('Whenever you cast an artifact creature spell, you gain 1 life.', 'Sunburst'),
        'Whenever you cast a Vampire creature spell, it gains bloodthirst 3.': ('Whenever you cast a Vampire creature spell, you gain 1 life.', 'Bloodthirst 3'),
        ELF: ('Whenever you cast an Elf spell, you gain 1 life.', 'haste'),
    }
    if text in choices:
        proxy, keyword = choices[text]
        native = scripts.define(replace(ability, text=proxy), ch)
        if native is None:
            return None
        grant: dict[str, Any] = {'do': 'grant', 'who': 'event_spell', 'duration': 'end_of_turn' if keyword == 'haste' else 'permanent'}
        grant['keywords' if keyword == 'haste' else 'abilities'] = [keyword]
        return {**native, 'effects': [grant, *([{'do': 'draw', 'who': 'you', 'n': 2}] if keyword == 'haste' else [])]}
    if text == GALEA:
        native = permissions.define_static('You may cast Aura and Equipment spells from the top of your library.', 'static',
                                           tuple(a.text for a in ch.abilities))
        trigger = {'kind': 'native', 'definition': {'object_filter': selectors.Selector(zones=('stack',), subtypes=('Equipment',)).key(),
                                                   'effects': [{'do': 'grant', 'who': 'event_spell', 'abilities': [GALEA_QUOTE], 'duration': 'permanent'}]}}
        return {**native, 'use_trigger': trigger} if native is not None else None
    return None
