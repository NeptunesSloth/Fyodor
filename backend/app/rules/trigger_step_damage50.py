"""Exact step-player conditions using native trigger and quantity semantics."""
from __future__ import annotations

import copy
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics

SKULL = ("At the beginning of each opponent's upkeep, this artifact deals 2 damage to that player "
         "unless they have exactly three or exactly four cards in hand.")
STALKER = ("At the beginning of each player's upkeep, if that player controls a nonblack, nonland permanent, "
           "this creature deals 1 damage to that player.")


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.kind != 'triggered' or ability.text not in (SKULL, STALKER):
        return None
    from app.rules import conditions, scripts

    base = ("At the beginning of each opponent's upkeep, this artifact deals 2 damage to that player."
            if ability.text == SKULL else
            "At the beginning of each player's upkeep, this creature deals 1 damage to that player.")
    native = scripts.define(replace(ability, text=base), ch)
    if native is None:
        return None
    out = copy.deepcopy(native)
    if ability.text == STALKER:
        condition = conditions.parse('that player controls a nonblack, nonland permanent', objects=True)
        if condition is None:
            return None
        out['if'] = condition
        out['effects'] = [{'do': 'only_if', 'cond': condition, 'skip': 1}, *out['effects']]
    else:
        out['effects'] = [{'do': 'only_if', 'cond': {'all': [
            {'not': {'as': 'event', 'cond': {'value': {'hand': 'you'}, 'op': '==', 'n': n}}}
            for n in (3, 4)]}, 'skip': 1}, *out['effects']]
    return out
