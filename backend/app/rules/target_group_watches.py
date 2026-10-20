"""Finite target groups watched until the creating ability's controller's next turn."""
from __future__ import annotations

import re
from typing import Any

_LINE = re.compile(r"^Choose (?P<targets>up to (?:two|three|four|\d+) target creatures)\. Until your next turn, whenever (?:either|any) of those creatures deals combat damage, you draw a card\.$", re.IGNORECASE)


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import events, language, watches

    match = _LINE.fullmatch(body.strip())
    if match is None:
        return None
    group = language.target_group(match['targets'].lower())
    if group is None:
        return None
    condition = events.parse_condition('a creature deals combat damage')
    if condition is None:
        return None
    condition = {**condition, 'source_batch': True}
    watch = watches.build(condition, 'you draw a card', once=False,
                          text='a chosen creature deals combat damage', bound='target', next_turn=True)
    return (watch[0], [group], False) if watch else None
