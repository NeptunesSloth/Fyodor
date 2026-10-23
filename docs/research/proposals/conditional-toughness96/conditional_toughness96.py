"""Conditional combat assignment uses current characteristics and native dynamic rules."""
from __future__ import annotations

from dataclasses import replace
from typing import Any


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors, statics

    text = scripts.self_text(ability.text, ch.name)
    bark = "As long as equipped creature's toughness is greater than its power, it assigns combat damage equal to its toughness rather than its power."
    footing = 'As long as enchanted creature has vigilance, it assigns combat damage equal to its toughness rather than its power.'
    if text in (bark, footing):
        is_equipment = text == bark
        subject = 'Equipped' if is_equipment else 'Enchanted'
        selector = (selectors.Selector(types=('Creature',), extras=('host_of_source', 'toughness_gt_power')) if is_equipment
                    else selectors.Selector(types=('Creature',), extras=('host_of_source',), with_keywords=('vigilance',)))
        native = statics.parse(f'{subject} creature assigns combat damage equal to its toughness rather than its power.')
        assert native is not None
        # Rule recipients are tested after layers, using the existing current-object
        # selector path. No early attached-condition cache or layer dependency is needed.
        return {**native, 'who': selector.key(), 'conditions': []}
    if text == 'Whenever you attack, you may pay 2 life. If you do, until end of turn, creatures you control with toughness greater than their power assign combat damage equal to their toughness rather than their power.':
        native = scripts.define(replace(ability, text="Whenever you attack, you may pay 2 life. If you do, creatures you control can't block this turn."), ch)
        assert native is not None
        # Native optional payment and its success guard are retained unchanged.
        effects = [({**effect, 'rules': ['assign_toughness_if_tougher']} if effect.get('do') == 'restrict' else effect)
                   for effect in native['effects']]
        return {**native, 'effects': effects}
    return None
