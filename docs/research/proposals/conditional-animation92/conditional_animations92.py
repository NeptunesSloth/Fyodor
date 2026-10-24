"""Exact conditional animations using native type, base, and rule components."""
from __future__ import annotations

from typing import Any

RELIC = 'Metalcraft — This artifact is a 5/5 Golem artifact creature as long as you control three or more artifacts.'
OPERATIVE = "As long as this creature is tapped, it's a Human Citizen with base power and toughness 1/1 and can't be blocked."
MASTER = "As long as Grand Master of Flowers has seven or more loyalty counters on him, he's a 7/7 Dragon God creature with flying and indestructible."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import statics

    if ability.kind == 'loyalty' and ability.text == "+1: Target creature without first strike, double strike, or vigilance can't attack or block until your next turn.":
        from dataclasses import replace

        from app.rules import scripts, selectors

        native = scripts.define(replace(ability, text="+1: Target creature can't attack or block until your next turn."), ch)
        assert native is not None
        target = selectors.Selector(types=('Creature',), without_keywords=('first strike', 'double strike', 'vigilance')).key()
        return {**native, 'target': {'what': target}}
    if ability.kind != 'static':
        return None
    if ability.text == RELIC:
        native = statics.parse('Enchanted creature is a Golem artifact creature with base power and toughness 5/5.')
        condition = statics.condition('you control three or more artifacts')
    elif ability.text == OPERATIVE:
        native = statics.parse('Enchanted creature is a Human Citizen with base power and toughness 1/1.')
        condition = statics.condition('~ is tapped')
        assert native is not None
        native = {**native, 'rules': ['cant_be_blocked']}
    elif ability.text == MASTER:
        native = statics.parse('Enchanted creature is a Dragon God creature with base power and toughness 7/7 and has flying and indestructible.')
        condition = statics.condition('there are seven or more loyalty counters on ~')
    else:
        return None
    assert native is not None and condition is not None
    # Existing own-type collection recognizes this native layer-4 marker.
    return {**native, 'who': 'self', 'attached_kind': None, 'conditions': [condition], 'add_subtypes': []}
