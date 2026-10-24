"""First actual kicked spell uses paid kicker authority, never synthetic own-effect aliases."""
from __future__ import annotations

from typing import Any


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    if ability.text == 'The first kicked spell you cast each turn costs {1} less to cast.':
        return {'kind': 'static', 'static': 'first_kicked77', 'effects': []}
    return None


def discount(state: Any, player: str, info: Any) -> int:
    from app.rules import history, permissions
    from app.rules.plan import Plan

    notes = [n for n in history.log_for(Plan.view(state, player, info)).casts if n.player == player]
    if any(n.kicked77 is not False for n in notes):
        return 0  # Unknown old authority cannot create a first-kicked discount.
    return sum(src.controller == player for src, _, _ in permissions._table_statics(state, info, {'first_kicked77'}))



def guard(state: Any, player: str, info: Any) -> None:
    from app.game.errors import ActionError
    from app.rules import history, permissions
    from app.rules.plan import Plan

    notes = [n for n in history.log_for(Plan.view(state, player, info)).casts if n.player == player]
    if any(n.kicked77 is True for n in notes) or not any(n.kicked77 is None for n in notes):
        return
    if any(src.controller == player for src, _, _ in permissions._table_statics(state, info, {'first_kicked77'})):
        raise ActionError('Earlier kicker payments this turn are unknown in this older save. Resolve this kicked spell cost manually.')
