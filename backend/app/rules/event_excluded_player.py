"""A chosen player target distinct from the player named by a triggering event."""
from __future__ import annotations

import re
from typing import Any


def parse(body: str, it: str | None, event_player: bool) -> tuple[list[dict[str, Any]], Any, bool] | None:
    m = re.fullmatch(r"Choose another target player\. (?P<source>~|This creature|This permanent) deals damage equal to that spell's mana value to the chosen player\.", body, re.IGNORECASE)
    if m is None or not event_player:
        return None
    from app.rules import scripts, selectors

    found = scripts.parse_effects(f"{m['source']} deals damage equal to that spell's mana value to target player.", it, event_player=True)
    if found is None or found[1] != 'player' or found[2]:
        return None
    return found[0], selectors.Selector(player='any', player_exclude='that_player').key(), False
