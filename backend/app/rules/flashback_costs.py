"""CR 601.2f, 702.34a: increases and reductions when paying a flashback cost."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import GameState
    from app.rules.characteristics import CardInfo


def definition(text: str) -> dict[str, Any] | None:
    m = re.fullmatch(r'flashback costs (?P<who>you|your opponents) pay cost \{(?P<n>\d+)\} (?P<direction>less|more)', text)
    return {'kind': 'static', 'static': 'flashback_cost_change', 'who': m['who'],
            'n': int(m['n']) * (-1 if m['direction'] == 'less' else 1), 'effects': []} if m else None


def changes(state: GameState, player: str, info: CardInfo) -> tuple[int, int]:
    from app.rules.permissions import _table_statics

    increase, reduction = 0, 0
    for source, _, d in _table_statics(state, info, {'flashback_cost_change'}):
        if (source.controller == player) != (d['who'] == 'you'):
            continue
        n = int(d['n'])
        increase += max(0, n)
        reduction += max(0, -n)
    return increase, reduction
