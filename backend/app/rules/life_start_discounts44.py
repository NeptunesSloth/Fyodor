"""Exact half-starting-life discount using native conditions."""
from typing import Any


def self_change(text: str) -> dict[str, Any] | None:
    text = text.strip().rstrip('.').lower().replace('~', 'this spell')
    if text != "this spell costs {2} less to cast if a player's life total is less than or equal to half their starting life total":
        return None
    one = {'static': 'life_vs_start', 'op': '<=', 'plus': 0, 'half': True}
    return {'dir': -1, 'n': 2, 'cond': {'any': [one, {**one, 'opp': True}]}}
