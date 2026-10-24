"""Exact named token instruction preserves the token's name through self-text rewriting."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

NOTEBOOK = 'Create Tamiyo\'s Notebook, a legendary colorless Book artifact token with "Spells you cast cost {2} less to cast" and "{T}: Draw a card."'


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'loyalty' or ability.text.partition(':')[2].strip() != NOTEBOOK:
        return None
    native = scripts.define(replace(ability, text=f'{ability.cost}: Draw a card.'), ch)
    parsed = scripts.parse_effects(NOTEBOOK + '.')
    if native is None or parsed is None:
        return None
    effects, target, optional = parsed
    return {**native, 'effects': effects, 'target': target, 'optional': optional}
