"""Persistent exact-card play permissions with spell-only color flexibility."""
from __future__ import annotations

from typing import Any

_BODY = ("Exile the top card of each opponent's library. You may play those cards for as long as they remain exiled. "
         "If you cast a spell this way, you may spend mana as though it were mana of any color to cast it.")


def parse(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    if body[:1].upper() + body[1:] != _BODY:
        return None
    return ([{'do': 'exile_top', 'n': 1, 'player': 'each_opponent', 'as': 'opponent_top'},
             {'do': 'grant_play', 'who': 'ref:opponent_top', 'play': True, 'cast': True,
              'until': 'permanent', 'from_exile': True, 'spend': 'color'}], None, False)
