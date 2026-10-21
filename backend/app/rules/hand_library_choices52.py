"""Fixed hidden-hand placements use native private selection and owner ordering."""
from __future__ import annotations

from typing import Any


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = body.strip()
    text = text[:1].upper() + text[1:]
    if text == 'Draw two cards, then put two cards from your hand on the bottom of your library.':
        return ([{'do': 'draw', 'who': 'you', 'n': 2},
                 {'do': 'put_back', 'n': 2, 'place': 'bottom'}], None, False)
    if text == ('Draw three cards, then put two cards from your hand both on top of your library '
                'or both on the bottom of your library.'):
        return ([{'do': 'draw', 'who': 'you', 'n': 3},
                 {'do': 'pick_one', 'options': [
                     {'label': 'Put both cards on top', 'effects': [{'do': 'put_back', 'n': 2, 'place': 'top'}]},
                     {'label': 'Put both cards on the bottom', 'effects': [{'do': 'put_back', 'n': 2, 'place': 'bottom'}]},
                 ]}], None, False)
    if text == 'Target player chooses three cards from their hand and puts them on top of their library in any order.':
        return ([{'do': 'put_back', 'n': 3, 'who': 'target', 'place': 'top'}], 'player', False)
    return None
