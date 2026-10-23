"""Bounded static cost changes read the actual caster, current spell and source's turn."""
from __future__ import annotations

from typing import Any


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import permissions, scripts

    text = scripts.self_text(ability.text, ch.name)
    if text == "Spells with flash you cast cost {1} less to cast and can't be countered.":
        native = permissions.define_static('spells with flash you cast cost {1} less to cast', 'static', ())
        return {**native, 'uncounterable': True} if native is not None else None
    if text == 'Each artifact spell costs {1} more to cast for each artifact its controller controls.':
        return {'kind': 'static', 'static': 'cost_modifier', 'caster': 'any', 'filter': permissions.spell_filter('artifact'),
                'delta': 0, 'caster_artifacts63': True, 'effects': []}
    if text == "During your turn, spells your opponents cast cost {1} more to cast and abilities your opponents activate cost {1} more to activate unless they're mana abilities.":
        native = permissions.define_static('during your turn, spells your opponents cast cost {1} more to cast', 'static', ())
        return {**native, 'opponent_nonmana63': True} if native is not None else None
    return None


def artifact_count(state: Any, info: Any, player: str) -> int:
    from app.rules.plan import Plan

    view = Plan.view(state, player, info)
    return sum(c.controller == player and c.zone.endswith(':battlefield') and 'Artifact' in view.ch(c).types
               for c in state.cards.values())


def ability_modifiers(state: Any, player: str, definitions: list[Any]) -> list[Any]:
    return [(source, {'delta': 1, 'filter': None, 'who': 'any', 'floor': False, 'nonmana': True})
            for source, _, definition in definitions if definition.get('opponent_nonmana63')
            and source.controller != player and state.turn.active_player == source.controller]
