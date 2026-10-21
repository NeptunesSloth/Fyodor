"""CR 601.2d: an X threshold changes the total before the casting division."""
from __future__ import annotations

import re
from typing import Any

_PATTERN = re.compile(
    r"(?P<first>~ deals X damage divided as you choose among (?P<targets>.+?))\. "
    r"If X is (?P<threshold>\d+) or more, ~ deals twice X damage divided as you choose among them instead\."
)


def parse(body: str, it: str | None = None, *, event_player: bool = False) -> tuple[list[dict[str, Any]], Any, bool] | None:
    m = _PATTERN.fullmatch(body)
    if m is None:
        return None
    from app.rules import scripts

    found = scripts._parse_effects_plain(m['first'] + '.', it, event_player=event_player)
    if found is None:
        return None
    effects, target, used = found
    groups = scripts._as_groups(target)
    if len(groups) != 1 or groups[0].get('divide') != {'what': 'damage', 'total': {'x': 1}}:
        return None
    group = groups[0]
    from app.rules import language

    # 115.6 / 601.2c: "up to" may choose zero even for positive X. 601.2d requires
    # a division among one or more chosen targets; every chosen target still gets at least one.
    printed = language.target_group(m['targets'])
    if printed is None:
        return None
    return effects, [{**group, 'min': printed['min'], 'divide': {'what': 'damage',
        'total': {'x_threshold_multiplier': {'at_least': int(m['threshold']), 'times': 2}},
        'allow_zero_targets': printed['min'] == 0}}], used
