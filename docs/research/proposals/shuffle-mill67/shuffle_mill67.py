"""Exact non-target graveyard choices and shuffle receipts before mill."""
from __future__ import annotations

from typing import Any

_SPIRAL = 'Shuffle all cards from your graveyard into your library. Target player mills that many cards.'
_STREAM = 'Target player mills four cards. You shuffle up to four cards from your graveyard into your library.'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import selectors
    if body.strip().casefold() == _SPIRAL.casefold():
        return [{'do': 'shuffle_library', 'who': 'you', 'zones': ['graveyard'], 'bind': 'shuffled67'},
                {'do': 'mill', 'who': 'target', 'n': {'ref_amount': 'shuffled67'}}], [{'what': 'player', 'min': 1, 'max': 1}], False
    if body.strip().casefold() == _STREAM.casefold():
        sel = selectors.Selector(card=True, zone_owner='you', zones=('graveyard',)).key()
        return [{'do': 'mill', 'who': 'target', 'n': 4},
                {'do': 'return_choice', 'sel': sel, 'n': 4, 'upto': True, 'to': 'choose', 'as': 'chosen67'},
                {'do': 'shuffle_library', 'who': 'you', 'zones': [], 'cards': 'ref:chosen67'}], [{'what': 'player', 'min': 1, 'max': 1}], False
    return None
