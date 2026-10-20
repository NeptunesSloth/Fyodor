"""Fight outcomes bound to one recipient, followed by mana (CR 120.10)."""
from __future__ import annotations

import re
from typing import Any

_FORM = re.compile(
    r"(?P<fight>Target creature you control fights target creature an opponent controls\.) "
    r"If the creature the opponent controls is dealt excess damage this way, add that much \{(?P<color>[WUBRGC])\}\."
    r"(?:\s+Until end of turn, you don't lose unspent (?P<name>white|blue|black|red|green|colorless) mana as steps and phases end\.)?", re.I)
_COLORS = dict(zip(('white', 'blue', 'black', 'red', 'green', 'colorless'), 'WUBRGC', strict=True))


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    m = _FORM.fullmatch(body.strip())
    if m is None:
        return None
    from app.rules import scripts

    found = scripts._parse_effects_plain(m['fight'])
    if found is None:
        return None
    effects, targets, optional = found
    bind = 'fight_excess'
    effects[0] = {**effects[0], 'bind_excess': bind, 'excess_on': effects[0]['with']}
    # Zero excess adds no mana, including when either target cannot fight.
    return ([*effects, {'do': 'add_mana', 'sym': m['color'].upper(), 'n': {'ref_amount': bind}},
             *([{'do': 'keep_mana', 'color': _COLORS[m['name'].lower()], 'until': 'end_of_turn'}] if m['name'] else [])], targets, optional)
