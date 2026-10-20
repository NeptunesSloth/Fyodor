"""CR 608.2h: the greatest count controlled by one eligible player, never a sum."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def parse(phrase: str) -> dict[str, Any] | None:
    from app.rules import selectors

    m = re.fullmatch(r'the (?:greatest|highest) number of (?P<what>.+) (?P<who>an opponent|a player) controls', phrase)
    if m is None:
        return None
    sel = selectors.parse(m['what'] + ' you control')
    if sel is None or sel.player is not None or sel.card or sel.zones != ('battlefield',) or sel.controller != 'you':
        return None
    return {'max_player_count': sel.key(), 'among': 'opponents' if m['who'] == 'an opponent' else 'players'}


def evaluate(plan: Plan, ctx: dict[str, Any], value: dict[str, Any]) -> int:
    from app.rules import values

    players = [p for p in plan.live() if value['among'] == 'players' or p != ctx['controller']]
    return max((values.evaluate(plan, {**ctx, 'controller': p}, {'count': value['max_player_count']}) for p in players), default=0)
