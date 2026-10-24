"""A World upkeep payment retains the affected player and original source."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

PILLAR = "At the beginning of each player's upkeep, that player may sacrifice a creature of their choice. If that player doesn't, they lose 5 life and you sacrifice this enchantment."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or ability.text != PILLAR:
        return None
    native = scripts.define(replace(ability, text="At the beginning of each player's upkeep, that player loses 5 life."), ch)
    if native is None:
        return None
    return {**native, 'effects': [
        {'do': 'optional_payment', 'who': 'event_player', 'cost': 'Sacrifice a creature', 'bind': 'pillar83_paid'},
        {'do': 'only_if', 'cond': {'succeeded': 'pillar83_paid', 'negate': True}, 'skip': 2},
        {'do': 'lose_life', 'who': 'event_player', 'n': 5}, {'do': 'sacrifice', 'who': 'self'}]}
