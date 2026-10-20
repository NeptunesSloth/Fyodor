"""CR 601.2b-c, 702.33c: one initial target plus one for each multikicker payment."""
from __future__ import annotations

import re
from typing import Any

LINE = re.compile(r'Choose (?P<first>any target|target creature), then choose another (?P<another>target|target creature) '
                  r'for each time this spell was kicked\. (?P<effect>.+)')


def definition(text: str, kind: str) -> dict[str, Any] | None:
    if kind != 'spell' or (m := LINE.fullmatch(text)) is None:
        return None
    creature = m['first'] == 'target creature'
    if m['another'] != ('target creature' if creature else 'target'):
        return None
    if m['effect'] == '~ deals X damage to each of them.':
        effect: dict[str, Any] = {'do': 'damage', 'who': 'target:0', 'n': {'x': 1}}
    elif creature and m['effect'] == 'Put X +1/+1 counters on each of them.':
        effect = {'do': 'add_counters', 'who': 'target:0', 'kind': '+1/+1', 'n': {'x': 1}}
    else:
        return None
    return {'kind': 'spell', 'target': None,
            'targets': [{'what': 'sel:{"types":["Creature"]}' if creature else 'any', 'min': 1, 'max': 1, 'per_kick_targets': 1}],
            'effects': [effect]}
