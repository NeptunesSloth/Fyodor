"""Earlier object targets bind later attachment selectors by original object identity."""
from __future__ import annotations

from typing import Any


def bind(plan: Any, spec: dict[str, Any], groups: list[list[Any]]) -> str:
    from app.rules import block_events, targets

    index = spec['object_of']
    selected = groups[index] if isinstance(index, int) and 0 <= index < len(groups) else []
    refs = [value if hasattr(value, 'object_id') else targets.ref(plan, value) for value in selected]
    context = {'targets': [ref.model_dump() for ref in refs]}
    return str(block_events.bind(plan, context, {'what': spec['what']})['what'])


TEXT = ('~ deals 5 damage to target creature. Exile up to one target Equipment attached to that creature. '
        'If that creature would die this turn, exile it instead.')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import scripts

    if scripts.self_text(ability.text, ch.name) != TEXT:
        return None
    native = scripts.define(replace(ability, text=ability.text.replace(
        ' If that creature would die this turn, exile it instead.', '')), ch)
    if native is None or len(native.get('targets', ())) != 2:
        return None
    first, equipment = native['targets']
    return {**native, 'targets': [first, {**equipment, 'of': 0, 'object_of': 0, 'requires_legal_group': 0}],
            'effects': [*native['effects'], {'do': 'exile_if_dies', 'who': 'target:0'}]}
