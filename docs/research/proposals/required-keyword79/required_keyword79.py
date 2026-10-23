"""A self graveyard permission requires the actual selected native keyword alternative."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import AbilityText, CardInfo, Characteristics

COMPOSITE = {
    'blitz—{2}{r}{r}, discard a card': ('blitz', 'pay {2}{R}{R} and discard a card'),
    'blitz—{2}{b}{b}, pay 2 life': ('blitz', 'pay {2}{B}{B} and pay 2 life'),
    'warp—{b}, pay 2 life': ('warp', 'pay {B} and pay 2 life'),
    'bestow—{r}, collect evidence 6': ('bestow', 'pay {R} and collect evidence 6'),
}


def composite_kind(line: str) -> str | None:
    found = COMPOSITE.get(line.lower().strip().rstrip('.'))
    return found[0] if found is not None else None


def keyword_definition(line: str) -> dict[str, Any] | None:
    from app.rules import alt_costs

    found = COMPOSITE.get(line.lower().strip().rstrip('.'))
    if found is None:
        return None
    tag, cost = found
    native = alt_costs.define(f"you may {cost} rather than pay ~'s mana cost")
    return {**native, 'tag': tag, **({'hand_only': True} if tag == 'warp' else {})} if native is not None else None


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    m = re.fullmatch(r'You may cast this card from your graveyard using its (blitz|warp|bestow) ability\.', ability.text)
    if m is None:
        return None
    return {'kind': 'static', 'static': 'permission', 'zone': 'graveyard', 'once': False, 'flash': False,
            'self': True, 'play': False, 'cast': True, 'filter': None, 'required_keyword79': m[1], 'effects': []}


def kind(state: GameState, player: str, card: CardInstance, ch: Characteristics) -> str | None:
    from app.rules import scripts

    if state.rules is None or card.owner != player or card.zone != f'{player}:graveyard':
        return None
    return next((d['required_keyword79'] for d in scripts.definitions(ch).values() if d.get('required_keyword79')), None)


def selected(state: GameState, player: str, card: CardInstance, ch: Characteristics,
             info: CardInfo | None, key: str | None) -> str | None:
    from app.rules import alt_costs

    tag = kind(state, player, card, ch)
    return tag if tag is not None and key is not None and info is not None and any(
        offer.key == key and offer.tag == tag for offer in alt_costs.offers(state, player, card, ch, info)) else None
