"""Exact self permission from a completed final numeric roll receipt."""
from __future__ import annotations

from typing import Any

_TEXT = ("You may cast this card from your graveyard as long as you've rolled a 6 this turn. "
         "If you cast it this way and it would be put into your graveyard, exile it instead.")


def definition(text: str) -> dict[str, Any] | None:
    if text != _TEXT:
        return None
    return {'kind': 'static', 'static': 'permission', 'zone': 'graveyard',
            'once': False, 'flash': False, 'self': True, 'play': False, 'cast': True,
            'filter': None, 'effects': [], 'exile_gy': 'all',
            'while': {'history': 'rolled_result', 'result': 6}}
