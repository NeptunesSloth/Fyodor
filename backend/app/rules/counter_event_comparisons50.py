"""Mixed entry/death watchers read the triggering object's native current/LKI reference."""
from __future__ import annotations

from typing import Any


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import events, scripts

    text = scripts.self_text(ability.text, ch.name)
    if text != ("Whenever another creature you control enters or dies, if that creature's power is greater than ~'s, "
                "put a +1/+1 counter on ~."):
        return None
    event = events.parse_condition('another creature you control enters or dies')
    assert event is not None
    return {'kind': 'triggered', 'trigger': 'event', 'cond': event,
            'if': {'object': 'event', 'beats_self': ['power']},
            'effects': [{'do': 'only_if', 'cond': {'object': 'event', 'beats_self': ['power']}, 'skip': 1},
                        {'do': 'add_counters', 'who': 'self', 'kind': '+1/+1', 'n': 1}],
            'optional': False, 'target': None}
