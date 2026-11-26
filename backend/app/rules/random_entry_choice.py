"""Finite automatic entering choices, sampled only by authoritative entry runners."""
from __future__ import annotations

import re
import secrets
from typing import Any


def parse(text: str) -> dict[str, Any] | None:
    if (m := re.fullmatch(r'As ~ enters, choose (?P<values>\d+(?:, \d+)*, or \d+) at random\.', text)) is None:
        return None
    values = re.findall(r'\d+', m['values'])
    return {'kind': 'replacement', 'replacement': 'enters_choice',
            'effects': [{'do': 'choose_value', 'who': 'you', 'what': 'number', 'options': values, 'random': True}]}


def answer(plan: Any, choice: dict[str, Any], player: str, card: str | None = None) -> str | None:
    if not choice.get('random'):
        return None
    from app.rules import randomness  # -- random choices (wave MBC-D) --
    value = str(randomness.choice(plan, plan.rng or secrets.SystemRandom(), choice['options'], kind='other', player=player))
    plan.note(f'Random entering choice: {value}', [card] if card else [], actor=player)
    return value
