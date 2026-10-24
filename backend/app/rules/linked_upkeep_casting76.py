"""Exact linked-player and upkeep-emblem permissions reuse native cast authorities."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics

IAN_DRAW = 'Whenever a player draws their second card each turn, that player exiles the top card of their library.'
IAN_CAST = "During each player's turn, that player may cast a spell from among the cards they don't own exiled with ~, and mana of any type can be spent to cast it."
KAYA = 'At the beginning of your upkeep, you may cast a legendary spell from your hand, from your graveyard, or from among cards you own in exile without paying its mana cost.'


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import permissions, scripts, selectors

    text = scripts.self_text(ability.text, ch.name)
    if text == IAN_DRAW:
        native = scripts.define(replace(ability, text=IAN_DRAW.replace('the top card', 'the top three cards')), ch)
        return {**native, 'effects': [{**e, 'n': 1, 'link': True} if e.get('do') == 'exile_top' else e
                                    for e in native['effects']]} if native is not None else None
    if text == IAN_CAST:
        native = permissions.define_static('You may cast spells from among cards exiled with ~.', 'static',
                                           tuple(a.text for a in ch.abilities))
        return {**native, 'any_player': True, 'during': 'your_turn', 'once': True,
                'once_per_player': True, 'spend': 'type',
                'filter': selectors.Selector(zones=('stack',), owner='opponent').key()} if native is not None else None
    if text == KAYA:
        native = scripts.define(replace(ability, text=KAYA.replace(
            'from your hand, from your graveyard, or from among cards you own in exile', 'from your hand')), ch)
        pool = selectors.Selector(zones=('hand', 'graveyard', 'exile'), zone_owner='you', owner='you', card=True).key()
        return {**native, 'effects': [{**e, 'zone': 'selector', 'pool_selector': pool} if e.get('do') == 'free_cast' else e
                                    for e in native['effects']]} if native is not None else None
    return None
