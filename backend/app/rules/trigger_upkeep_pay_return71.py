"""The active player pays or chooses an own permanent; the trigger keeps its controller."""
from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any

TEXTS = frozenset({
    "At the beginning of each player's upkeep, that player may pay 2 life. If they don't, they return a permanent they control to its owner's hand.",
    "At the beginning of each player's upkeep, that player returns a permanent they control to its owner's hand unless they pay 2 life.",
})
BASE = ("At the beginning of each player's upkeep, you may pay 2 life. "
        "If you don't, return a permanent you control to its owner's hand.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or ability.text not in TEXTS:
        return None
    native = scripts.define(replace(ability, text=BASE), ch)
    if native is None:
        return None
    out = copy.deepcopy(native)
    effects = out.get('effects') or []
    if ([e.get('do') for e in effects] != ['optional_payment', 'only_if', 'player_chooses', 'bounce']
            or any(e.get('who') != 'you' for e in effects if e['do'] in ('optional_payment', 'player_chooses'))):
        return None
    for effect in effects:
        if effect['do'] in ('optional_payment', 'player_chooses'):
            effect['who'] = 'event_player'
    return out
