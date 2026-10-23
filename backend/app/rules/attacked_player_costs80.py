"""Exact own-spell cost for the distinct players the caster is currently attacking."""
from __future__ import annotations

from typing import Any


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    if ability.text == "This spell costs {1} less to cast for each opponent you're attacking.":
        return {'kind': 'static', 'static': 'self_cost', 'change': {'dir': -1, 'value': {'players_attacked': 1, 'by': 'you'}}, 'effects': []}
    return None
