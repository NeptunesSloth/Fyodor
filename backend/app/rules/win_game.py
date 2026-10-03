"""-- win the game (wave 6D) -- "At the beginning of your upkeep, if you have 40 or more life, you win the game."
(Felidar Sovereign, Revel in Riches, Test of Endurance, Epic Struggle, Biovisionary …)

104.2b: an effect may state that a player wins the game; the game ends at once (104.1) — every other player has lost
it (replace._win, the same choke point as Thassa's Oracle and Laboratory Maniac's replacement). The condition is the
trigger's intervening "if" (603.4), read by the ordinary condition grammar. A permanent saying a player "can't win the
game" (104.2b: an effect that stops the win, not modelled) leaves the win to the players, as for Thassa's Oracle.
Only "you" (the ability's controller) win here.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_PATTERN = re.compile(r"^you win the game$")


def _build(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "win_game", "who": "you"}], None


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_PATTERN, _build)]


def win_game(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import characteristics as chars
    from app.rules.replace import _win

    pid = ctx["controller"]
    blockers = [c for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and not c.face_down
                and "can't win the game" in " ".join(ab.text for ab in chars.of(c, plan.info).abilities)]
    if blockers:
        plan.note(f"{plan.name(pid)} would win the game, but {blockers[0].name} says a player can't: resolve it by hand")
        return True
    _win(plan, pid)
    return True


PRIMITIVES = {"win_game": win_game}
