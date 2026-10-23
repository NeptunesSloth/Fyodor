"""Brokkos grants its own graveyard only for a selected native mutate cost."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import AbilityText, CardInfo, Characteristics

TEXT = 'You may cast this card from your graveyard using its mutate ability.'


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.text != TEXT:
        return None
    return {'kind': 'static', 'static': 'permission', 'zone': 'graveyard', 'once': False, 'flash': False,
            'self': True, 'play': False, 'cast': True, 'filter': None, 'required_mutate75': True, 'effects': []}


def candidate(state: GameState, player: str, card: CardInstance, ch: Characteristics) -> bool:
    from app.game.state import zone_key
    from app.rules import scripts

    return state.rules is not None and card.owner == player and card.zone == zone_key(player, 'graveyard') \
        and any(d.get('required_mutate75') for d in scripts.definitions(ch).values())


def selected(state: GameState, player: str, card: CardInstance, ch: Characteristics,
             info: CardInfo | None, key: str | None) -> bool:
    from app.rules import alt_costs

    return key is not None and info is not None and candidate(state, player, card, ch) \
        and any(offer.key == key and offer.tag == 'mutate' for offer in alt_costs.offers(state, player, card, ch, info))
