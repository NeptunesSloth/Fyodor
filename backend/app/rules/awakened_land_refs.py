"""Reveal lands into play, then conditionally untap only those new permanents."""
from __future__ import annotations

import re
from typing import Any

_BODY = re.compile(r"Reveal the top X cards of your library\. Put all land cards from among them onto the battlefield tapped "
                   r"and the rest on the bottom of your library in a random order\.\s+(?:Spell mastery — )?"
                   r"If there are two or more instant and/or sorcery cards in your graveyard, untap those lands\.", re.I)


def parse(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    from app.rules import conditions, selectors

    if _BODY.fullmatch(body) is None:
        return None
    lands = selectors.parse('land cards')
    battlefield = selectors.parse('lands')
    mastery = conditions.parse('there are two or more instant and/or sorcery cards in your graveyard')
    assert lands is not None and battlefield is not None and mastery is not None
    return ([{'do': 'look_top', 'n': {'x': 1}, 'player': 'you', 'reveal': True},
             {'do': 'pick_looked', 'n': 99, 'sel': lands.key(), 'to': 'battlefield_tapped',
              'optional': False, 'reveal': False, 'as': 'awakened_lands'},
             {'do': 'rest_looked', 'to': 'bottom_random'},
             {'do': 'only_if', 'cond': mastery, 'skip': 1},
             {'do': 'untap', 'who': 'ref:awakened_lands|' + battlefield.key()}], None, False)
