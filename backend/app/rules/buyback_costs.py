"""CR 118.7, 702.27a: reduce the buyback component before adding the spell's other costs."""
from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.rules import mana as M

if TYPE_CHECKING:
    from app.game.state import GameState
    from app.rules.characteristics import CardInfo


def definition(text: str) -> dict[str, Any] | None:
    m = re.fullmatch(r'buyback costs cost \{(?P<n>\d+)\} less', text)
    return {'kind': 'static', 'static': 'buyback_cost_reduction', 'n': int(m['n']), 'effects': []} if m else None


def reduced(state: GameState, info: CardInfo, cost: str) -> M.ManaCost:
    from app.rules.permissions import _table_statics

    n = sum(int(d['n']) for _, _, d in _table_statics(state, info, {'buyback_cost_reduction'}))
    base = M.parse_cost(cost)
    return replace(base, generic=max(0, base.generic - n))
