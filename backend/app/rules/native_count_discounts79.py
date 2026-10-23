"""Exact own-spell reductions composed from native current characteristics and cast history."""
from __future__ import annotations

from typing import Any


def self_change(text: str) -> dict[str, Any] | None:
    if text == 'this spell costs {1} less to cast for each spell your opponents have cast this turn':
        return {'dir': -1, 'value': {'minus': [{'spells_cast': 'all'}, {'spells_cast': 'you'}]}}
    if text == 'this spell costs {2} less to cast if you control at least two creatures that share a creature type':
        from app.rules import selectors

        own = selectors.parse('creatures you control')
        if own is not None:
            return {'dir': -1, 'n': 2, 'cond': {'value': {'shared_type': 1, 'of': own.key()}, 'op': '>=', 'n': 2}}
    return None
