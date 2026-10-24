"""Exact discounts evaluated against the actual native chosen spell targets at cost lock."""
from __future__ import annotations

from typing import Any


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    if ability.text == 'This spell costs {1} less to cast if it targets an attacking or tapped creature.':
        from app.rules.selectors import Selector

        choices = (Selector(types=('Creature',), attacking=True), Selector(types=('Creature',), tapped=True))
        return {'kind': 'static', 'static': 'self_cost', 'change': {'dir': -1, 'n': 1,
                'targets': Selector(either=tuple(s.key() for s in choices)).key()}, 'effects': []}
    if ability.text == 'This spell costs {3} less to cast if it targets a creature whose controller has eight or more cards in their graveyard.':
        return {'kind': 'static', 'static': 'self_cost', 'change': {'dir': -1, 'n': 3, 'target_controller_graveyard_min81': 8}, 'effects': []}
    return None
