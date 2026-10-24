"""Exact conditional statics expressed through existing native grant predicates."""
from __future__ import annotations

from typing import Any

SHORT = 'As long as enchanted permanent is a creature, it gets -3/-0 and loses flying.'
GROND = "As long as it's your turn and you control an Army, Grond is an artifact creature."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import statics

    if ability.kind != 'static':
        return None
    if ability.text == SHORT:
        # Native attached_kind=creature already restricts this grant to creature hosts.
        return statics.parse('Enchanted creature gets -3/-0 and loses flying.')
    if ability.text == GROND:
        native = statics.parse("As long as it's your turn, ~ is an artifact creature.")
        army = statics.condition('you control an Army')
        assert native is not None and army is not None
        return {**native, 'conditions': [*native['conditions'], army]}
    return None
