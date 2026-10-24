"""Exact compound attack headers and effects retain native event-time conditions."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

IRON = 'Whenever ~ or a commander you control attacks alone, return target artifact card from your graveyard to the battlefield.'
WARG = 'Whenever ~ attacks while you control a creature with power 4 or greater, until end of turn, ~ gets +1/+0 and creatures you control gain trample.'


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered':
        return None
    text = scripts.self_text(ability.text, ch.name)
    if text == IRON:
        first = scripts.define(replace(ability, text=IRON.replace(' or a commander you control', '')), ch)
        second = scripts.define(replace(ability, text=IRON.replace('~ or a commander you control', 'a commander you control')), ch)
        if first is None or second is None:
            return None
        return {**first, 'cond': {'event': 'either', 'subject': 'mixed', 'conds': [first['cond'], second['cond']]}}
    if text == WARG:
        proxy = 'Whenever ~ attacks while you control a creature with power 4 or greater, ~ gets +1/+0 until end of turn. Creatures you control gain trample until end of turn.'
        return scripts.define(replace(ability, text=proxy), ch)
    return None
