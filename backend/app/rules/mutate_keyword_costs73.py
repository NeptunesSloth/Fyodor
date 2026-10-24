"""Pollywog composes native keyword spell pricing and event/LKI intervening conditions."""
from __future__ import annotations

from dataclasses import replace
from typing import Any


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import permissions, scripts

    if ability.text == 'Each creature spell you cast costs {1} less to cast if it has mutate.':
        native = permissions.define_static('Creature spells you cast cost {1} less to cast.', 'static', ())
        key = permissions.spell_filter('creature', 'with mutate')
        return {**native, 'filter': key} if native is not None and key is not None else None
    if ability.text == 'Whenever you cast a creature spell, if it has mutate, draw a card, then discard a card.':
        native = scripts.define(replace(ability, text='Whenever you cast a creature spell with mutate, draw a card, then discard a card.'), ch)
        return {**native, 'if': {'object': 'event', 'has': 'mutate'}} if native is not None else None
    return None
