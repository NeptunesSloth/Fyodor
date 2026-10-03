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
    from app.rules.replace import _win

    pid = ctx["controller"]
    if (unread := _unread_blocker(plan, "win")) is not None:
        plan.note(f"{plan.name(pid)} would win the game, but {unread} says a player can't: resolve it by hand")
        return True
    _win(plan, pid)  # (a player who "can't win the game", 104.2b: game_result.cannot_win there)
    return True


def _unread_blocker(plan: Plan, what: str) -> str | None:
    """-- review (wave 11C) -- the name of a permanent saying a player "can't {win|lose} the game" in a wording the engine
    doesn't read (app/rules/game_result.py reads "You can't lose the game and your opponents can't win the game" and its
    mirror, applied by replace._win and by sba / lose_game), or None: such a wording leaves the result to the players."""
    from app.rules import characteristics as chars
    from app.rules import game_result

    for c in plan.state.cards.values():
        if not c.zone.endswith(":battlefield") or c.face_down or not plan.in_game(c):
            continue
        for ab in chars.of(c, plan.info).abilities:
            if f"can't {what} the game" in ab.text and game_result.static_definition(ab.text) is None:
                return c.name
    return None


def lose_game(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """-- lose the game (wave 11C) -- 104.3e: an effect may state that a player loses the game. They leave the game at once
    (104.3, 800.4a: as for a state-based loss, app/rules/sba.py): their permanents and spells go, and the last player left wins.
    A permanent saying a player "can't lose the game" (104.3b, not modelled) leaves it to the players, as for winning."""
    from app.rules import game_result
    from app.rules.effects import _players
    from app.rules.leave import leave_game
    from app.rules.plan import live_players

    r = plan.rules
    losers = [p for p in _players(plan, ctx, e["who"]) if p in plan.live()]
    if losers and (unread := _unread_blocker(plan, "lose")) is not None:
        plan.note(f"{plan.name(losers[0])} would lose the game, but {unread} says a player can't: resolve it by hand")
        return True
    for pid in losers:  # (wave 10B) one who "can't lose the game" (104.3) stays, as for a state-based loss (sba.py)
        if game_result.cannot_lose(plan, pid):
            plan.note(f"{plan.name(pid)} would lose the game, but can't")
    losers = [p for p in losers if not game_result.cannot_lose(plan, p)]
    for pid in losers:
        r.lost[pid] = "an effect"
        plan.note(f"{plan.name(pid)} loses the game (an effect)")
    for pid in losers:
        leave_game(plan, pid)
    left = live_players(plan.state)
    if losers and len(left) == 1 and r.winner is None:
        r.winner = left[0]
        plan.note(f"{plan.name(left[0])} wins the game")
    return True


PRIMITIVES = {"win_game": win_game, "lose_game": lose_game}
