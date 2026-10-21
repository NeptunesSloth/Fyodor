"""Nether Spirit retains native graveyard identity and intervening count gates."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = ('At the beginning of your upkeep, if this card is the only creature card in your graveyard, '
        'you may return this card to the battlefield.')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    if ability.kind != 'triggered' or ability.text != TEXT:
        return None
    native = scripts.define(replace(ability, text=TEXT.replace(
        'the only creature card in your graveyard', 'in your graveyard')), ch)
    if native is None:
        return None
    condition = {'all': [native['if'],
                        {'value': {'count': selectors.Selector(zones=('graveyard',), types=('Creature',), owner='you').key()},
                         'op': '==', 'n': 1}]}
    return {**native, 'if': condition, 'effects': [
        {'do': 'only_if', 'cond': condition, 'skip': 1}, *native['effects'][1:]]}
