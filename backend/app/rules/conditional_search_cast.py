"""A private search, conditional free cast, then return the card if it wasn't cast."""
from __future__ import annotations

import re
from typing import Any

_PATTERN = re.compile(
    r"^Search your library for a card, exile it face down, then shuffle\. "
    r"If this spell was (?:bargained|kicked), you may cast the exiled card without paying its mana cost "
    r"if that spell's mana value is (?P<mv>\d+) or less\. "
    r"Put the exiled card into your hand if it wasn't cast this way\.$"
)


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import selectors

    searched = re.fullmatch(r"Search your library for (?P<what>an? .+? card(?: with .+?)?) and cast that card without paying its mana cost\. Then shuffle\.", body.strip())
    if searched:
        phrase = re.sub(r"^an? ", "", searched['what'])
        sel = selectors.parse(phrase + ' in your library')
        if sel is None:
            return None
        return ([{'do': 'search', 'who': 'you', 'sel': sel.key(), 'label': phrase, 'max': 1,
                  'to': 'library', 'shuffle': False, 'as': 'searched_card'},
                 {'do': 'free_cast', 'zone': 'that', 'who': 'ref:searched_card', 'filter': None,
                  'n': 1, 'required': True, 'source_zone': 'library'},
                 {'do': 'shuffle_library', 'who': 'you'}], None, False)
    m = _PATTERN.fullmatch(body.strip())
    if m is None:
        return None
    sel = selectors.parse('card in your library')
    assert sel is not None
    return ([{'do': 'search', 'who': 'you', 'sel': sel.key(), 'label': 'card', 'max': 1,
              'to': 'exile', 'face_down': True, 'reveal': False, 'upto': False, 'as': 'searched_card'},
             {'do': 'only_if', 'cond': {'object': 'self', 'cast': {'kicked': True}}, 'skip': 1},
             {'do': 'free_cast', 'zone': 'that', 'who': 'ref:searched_card', 'filter': None,
              'mv': int(m['mv']), 'n': 1, 'optional': True, 'did': 'searched_cast'},
             {'do': 'only_if', 'cond': {'succeeded': 'searched_cast', 'negate': True}, 'skip': 1},
             {'do': 'return_card', 'who': 'ref:searched_card', 'to': 'hand'}], None, False)
