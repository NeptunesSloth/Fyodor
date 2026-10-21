"""A fight's named opposing target keeps its own turn-long exile replacement."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

BURN = ('~ deals X damage to any target. If a creature is dealt damage this way, '
        'it loses indestructible until end of turn. If that creature would die this turn, exile it instead.')

TEXTS = {
    'When ~ enters, it fights up to one target creature an opponent controls. If that creature would die this turn, exile it instead.':
        (' If that creature would die this turn, exile it instead.', 'target:0'),
    'Target creature you control fights target creature an opponent controls. If the creature an opponent controls would die this turn, exile it instead.':
        (' If the creature an opponent controls would die this turn, exile it instead.', 'target:1'),
    "{1}, Sacrifice an Aura attached to ~: ~ fights target creature you don't control. If that creature would die this turn, exile it instead. Activate only as a sorcery.":
        (' If that creature would die this turn, exile it instead.', 'target'),
}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    normalized = scripts.self_text(ability.text, ch.name)
    if normalized == BURN:
        native = scripts.define(replace(ability, text=ability.text.replace(
            ' If that creature would die this turn, exile it instead.', '')), ch)
        if native is None or len(native.get('effects', ())) != 3:
            return None
        damage, condition, removal = native['effects']
        if damage.get('do') != 'damage' or condition.get('do') != 'only_if' or removal.get('do') != 'grant':
            return None
        return {**native, 'effects': [damage, {**condition, 'skip': 2}, removal,
                {'do': 'exile_if_dies', 'who': 'target'}]}
    match = TEXTS.get(normalized)
    if match is None:
        return None
    sentence, target = match
    native = scripts.define(replace(ability, text=ability.text.replace(sentence, '')), ch)
    if native is None or not any(e.get('do') in ('fight', 'damage') for e in native.get('effects', ())):
        return None
    return {**native, 'effects': [*native['effects'],
            {'do': 'exile_if_dies', 'who': target}]}
