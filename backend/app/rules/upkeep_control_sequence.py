"""CR 608.2c, 122.6: the named upkeep player controls, untaps and puts the counter."""
from __future__ import annotations

from typing import Any


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    body = body.strip()
    body = body[:1].upper() + body[1:]
    if body != ("That player gains control of ~, untaps it, and puts a +1/+1 counter on it. "
                        "It gains haste until end of turn."):
        return None
    return ([{'do': 'gain_control', 'who': 'self', 'to': 'event_player'},
             {'do': 'untap', 'who': 'self'},
             {'do': 'add_counters', 'who': 'self', 'kind': '+1/+1', 'n': 1, 'by': 'event_player'},
             {'do': 'grant', 'who': 'self', 'keywords': ['haste']}], None, False)
