"""Bound non-target choices delegated to existing native choice/move effects."""
from __future__ import annotations

import copy
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import AbilityText, Characteristics

STOMPER = "When this creature enters, return up to two lands you control to their owner's hand."
GARGANTUAN = "When this creature enters, put a creature you control on top of its owner's library."


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    if ability.kind != 'triggered' or ability.text not in (STOMPER, GARGANTUAN):
        return None
    from app.rules import scripts, selectors

    base = ("When this creature enters, return two permanents you control to their owner's hand."
            if ability.text == STOMPER else
            "When this creature enters, return a permanent you control to its owner's hand.")
    native = scripts.define(replace(ability, text=base), ch)
    if native is None:
        return None
    out = copy.deepcopy(native)
    choice, move = out['effects']
    if choice.get('do') != 'player_chooses' or move.get('do') != 'bounce':
        return None
    kind = 'Land' if ability.text == STOMPER else 'Creature'
    choice.update(sel=selectors.Selector(types=(kind,)).key(), label=kind.lower())
    if ability.text == STOMPER:
        choice.update(upto=True, optional=True)
    elif ability.text == GARGANTUAN:
        move.update(do='to_library', place='top')
    return out
