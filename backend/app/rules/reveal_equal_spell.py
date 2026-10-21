"""Optional top-card reveal followed by face-aware equal-mana-value casting."""
from __future__ import annotations

from typing import Any

_BODY = ('You may reveal the top card of your library. If you do, you may cast that card without paying its mana cost '
         'if the two spells have the same mana value.')


def parse(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    if body[:1].upper() + body[1:] != _BODY:
        return None
    return ([{'do': 'look_top', 'n': 1, 'player': 'you', 'reveal': True, 'optional': True, 'as': 'equal_spell_top'},
             {'do': 'free_cast', 'zone': 'that', 'who': 'ref:equal_spell_top', 'n': 1,
              'mv': {'mana_value': 'event'}, 'mv_eq': True, 'exact_refs': True},
             {'do': 'hide_revealed', 'refs': 'equal_spell_top', 'zone': 'library'}], None, False)
