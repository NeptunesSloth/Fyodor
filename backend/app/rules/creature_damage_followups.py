"""Creature-source damage and exact-source battlefield guards."""
from __future__ import annotations

from typing import Any


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = body.strip().rstrip('.')
    text = text[:1].upper() + text[1:]
    from app.rules import player_relative, scripts

    if text == 'Target creature you control deals X damage to any other target and X damage to itself, where X is its power':
        base = scripts.parse_effects('Target creature you control deals damage equal to its power to any target.')
        if base is not None:
            damage = base[0][0]
            groups = [dict(group) for group in base[1]]
            groups[1]['distinct_from'] = [0]
            return [{**damage, 'with_next': True}, {**damage, 'who': 'target:0'}], groups, False
    if text == 'Tap enchanted creature. It deals damage to you equal to its power':
        return scripts.parse_effects('Tap enchanted creature. Enchanted creature deals damage equal to its power to you.')
    if text == 'Target creature deals damage to itself equal to its power. If that creature has flying, it deals twice that much damage to itself instead':
        base = scripts.parse_effects('Target creature deals damage equal to its power to itself.')
        if base is not None:
            damage = base[0][0]
            return [{'do': 'only_if', 'cond': {'object': 'target', 'has': 'flying'}, 'skip': 1, 'bind': 'flying'},
                    {**damage, 'n': {'times': [2, damage['n']]}},
                    {'do': 'only_if', 'cond': {'flag': 'flying', 'negate': True}, 'skip': 1}, damage], base[1], False
    if text == "Target creature deals damage equal to its power to itself. If that creature is attacking, ~ deals 2 damage to that creature's controller":
        base = scripts.parse_effects('Target creature deals damage equal to its power to itself.')
        if base is not None:
            return [*base[0], {'do': 'only_if', 'cond': {'object': 'target', 'test': 'attacking'}, 'skip': 1},
                    {'do': 'damage', 'who': player_relative.TP + '0', 'n': 2}], base[1], False
    prefix = 'If ~ is on the battlefield, '
    if text.startswith(prefix):
        tail = text[len(prefix):]
        if tail == 'it deals damage equal to its power to target attacking creature. That creature deals damage equal to its power to ~':
            base = scripts.parse_effects('~' + tail[2:] + '.')
            if base is not None:
                return [{'do': 'only_if', 'cond': {'object': 'self', 'test': 'on_battlefield'}, 'skip': len(base[0])}, *base[0]], base[1], False
    return None


def definition(text: str, kind: str) -> dict[str, Any] | None:
    if kind != 'triggered' or text != "When ~ enters, if it's on the battlefield, it deals damage equal to its power to target creature an opponent controls and that creature deals damage equal to its power to ~.":
        return None
    from app.rules import scripts

    base = scripts.parse_effects('~ deals damage equal to its power to target creature an opponent controls. That creature deals damage equal to its power to ~.')
    if base is None:
        return None
    return {'kind': 'triggered', 'trigger': 'enters_self', 'if': {'object': 'self', 'test': 'on_battlefield'},
            'effects': [{'do': 'only_if', 'cond': {'object': 'self', 'test': 'on_battlefield'}, 'skip': len(base[0])}, *base[0]],
            'optional': False, **scripts.target_fields(base[1])}
