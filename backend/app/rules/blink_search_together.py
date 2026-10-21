"""CR 608.2c / 603.6a: exile, find a land, then put both onto the battlefield together."""
from __future__ import annotations

from typing import Any


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import selectors

    body = body.strip()
    if body[:1].upper() + body[1:] != ('Exile up to one target creature you own, then search your library for a basic land card. '
                        'Put both cards onto the battlefield under your control, then shuffle.'):
        return None
    creature = selectors.parse('creature you own')
    land = selectors.parse('basic land card in your library')
    assert creature is not None and land is not None
    return ([{'do': 'exile', 'who': 'target', 'as': 'blinked_creature'},
             {'do': 'search', 'who': 'you', 'sel': land.key(), 'label': 'basic land card', 'max': 1,
              'to': 'choose', 'reveal': False, 'upto': False, 'shuffle': False, 'as': 'searched_land'},
             {'do': 'return_card', 'who': 'ref:blinked_creature', 'also': 'ref:searched_land',
              'to': 'battlefield', 'under': 'you', 'tapped': False},
             {'do': 'shuffle_library', 'who': 'you', 'zones': []}],
            [{'what': creature.key(), 'min': 0, 'max': 1}], False)
