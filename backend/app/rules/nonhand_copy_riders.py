"""Permanent-only riders on native optional and paid spell copies."""
from __future__ import annotations

from typing import Any


def parse(body: str, it: str | None, event_player: bool) -> tuple[list[dict[str, Any]], Any, bool] | None:
    separator = ". If the copy is a permanent spell, it gains "
    if separator not in body:
        return None
    prefix, gain = body.strip().split(separator, 1)
    spider = prefix.lower() == "you may copy it. if you do, you may choose new targets for the copy"
    paid = prefix.lower() == "you may pay {1}{u/r}. if you do, copy that spell and you may choose new targets for the copy"
    if not spider and not paid:
        return None
    from app.rules import scripts

    if spider:
        prefix = "You may copy that spell and you may choose new targets for the copy"
    found = scripts.parse_effects(prefix + ".", it, event_player=event_player)
    gained = scripts.parse_effects("The copy gains " + gain)
    if found is None or found[1] is not None or gained is None or gained[1] is not None or gained[2]:
        return None
    if len(gained[0]) != 1 or gained[0][0].get("do") != "copy_gain":
        return None
    effects = [dict(e) for e in found[0]]
    copies = [e for e in effects if e.get("do") == "copy_spell"]
    if len(copies) != 1:
        return None
    if spider:
        copies[0]["bind"] = "copied"
    else:
        # The existing payment gate must also skip the appended copy rider.
        for effect in effects:
            if effect.get("do") == "only_if":
                effect["skip"] = int(effect["skip"]) + 1
    return [*effects, {**gained[0][0], "if_permanent": True}], None, found[2]
