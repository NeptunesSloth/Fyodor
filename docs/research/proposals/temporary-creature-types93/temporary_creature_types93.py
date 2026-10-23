"""Compound temporary pumps and creature-subtype changes share one object binding."""
from __future__ import annotations

import re
from typing import Any

_PATTERN = re.compile(
    r'(?P<lead>Until end of turn, )?(?P<subject>Up to two target creatures each|Creatures target player controls|creatures you control|Target creature) '
    r'(?P<verb>gets?|get) (?P<p>[+-]\d+)/(?P<t>[+-]\d+) and (?P<action>gains?|loses?) all creature types(?P<end> until end of turn)?\.'
)


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind == 'activated' and ability.cost == '{T}':
        typed = re.fullmatch(r'\{T\}: Target creature (?P<action>gains|loses) all creature types until end of turn\.', ability.text)
        if typed is not None:
            change: dict[str, Any] = {'do': 'become', 'who': 'target', 'types': [], 'duration': 'end_of_turn'}
            if typed['action'] == 'gains':
                change['all_creature_types'] = True
            else:
                change['creature_types'] = []
            return {'kind': 'activated', 'cost': '{T}', 'effects': [change], 'target': {'what': 'creature'}}
    if ability.kind != 'spell'  or (match := _PATTERN.fullmatch(ability.text)) is None:
        return None
    if bool(match['lead']) == bool(match['end']):
        return None
    text = f"{match['subject']} {match['verb']} {match['p']}/{match['t']} until end of turn"
    parsed = scripts._clause(text.lower())
    if parsed is None:
        return None
    effects, target = parsed
    if len(effects) != 1 or effects[0].get('do') != 'pump':
        return None
    groups: list[dict[str, Any]] = []
    effects = scripts._add_groups(groups, effects, target)
    effects, target = scripts._finish_targets(effects, groups)
    # 611.2c: both parts affect exactly the objects selected as resolution begins.
    pump = {**effects[0], 'as': 'typed93'}
    compound_change: dict[str, Any] = {'do': 'become', 'who': 'ref:typed93', 'types': [], 'duration': 'end_of_turn'}
    if match['action'].startswith('gain'):
        compound_change['all_creature_types'] = True
    else:
        compound_change['creature_types'] = []
    return {'kind': 'spell', 'effects': [pump, compound_change], **scripts.target_fields(target)}
