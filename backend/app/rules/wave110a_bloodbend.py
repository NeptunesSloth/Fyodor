"""-- wave 110A -- Secret of Bloodbending: "You control target opponent during their next combat phase. If this spell's additional cost was paid,
you control that player during their next turn instead."

723.1 / 2025-10-02 rulings: the same player control as Mindslaver (player_control.control_player) but limited to the controlled player's next
combat phase unless the optional waterbend {10} (701.67, wave 103) was paid; a later effect on the same player overwrites it (723.1a)."""
from __future__ import annotations

from typing import Any

LINE = ("You control target opponent during their next combat phase. If this spell's additional cost was paid, "
        "you control that player during their next turn instead.")


def _build() -> tuple[list[dict[str, Any]], Any, bool]:
    from app.rules import scripts

    parsed = scripts.parse_effects("You control target opponent during their next turn.")
    assert parsed is not None
    effects, target, flag = parsed
    return [{**effects[0], "combat_unless110a": {"object": "self", "cast": {"waterbend_paid103": True}}}], target, flag


BUILDERS = {LINE: _build}
