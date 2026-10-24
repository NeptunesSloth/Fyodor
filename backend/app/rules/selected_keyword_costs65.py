"""Keyword-specific prices retain native total-cost order and current source-turn scope."""
from __future__ import annotations

from typing import Any


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, statics

    text = scripts.self_text(ability.text, ch.name)
    if text == 'Dash costs you pay cost {2} less.':
        return {'kind': 'static', 'static': 'dash_reduction65', 'effects': []}
    if text == 'During your turn, creatures you control have first strike and equip abilities you activate cost {1} less to activate.':
        native = statics.parse('During your turn, creatures you control have first strike.')
        return {**native, 'own_turn_equip65': True} if native is not None else None
    return None


def dash_discount(state: Any, player: str, info: Any) -> int:
    from app.rules import permissions

    return 2 * sum(source.controller == player for source, _, _ in permissions._table_statics(state, info, {'dash_reduction65'}))


def ability_modifiers(state: Any, player: str, definitions: list[Any]) -> list[Any]:
    return [(source, {'delta': -1, 'filter': None, 'who': 'you', 'floor': False, 'equip': True})
            for source, _, definition in definitions if definition.get('own_turn_equip65')
            and source.controller == player and state.turn.active_player == source.controller]
