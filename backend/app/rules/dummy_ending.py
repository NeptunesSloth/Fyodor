"""-- target dummy -- a test table's game ends once only target dummies are left in it (app/game/dummy.py).

A dummy never plays: it only passes and answers what it's asked. When the last player who isn't a dummy has lost or conceded (or left)
and two or more dummies are still in the game, nothing could ever happen again but the dummies' empty turns, round after round until
their libraries run out. So the game ends there: the dummies win (104.2a gives the one player left the win; with several dummies the
test is simply over). It is recorded as the rules' ``draw_reason`` with :data:`DUMMIES_WIN`, the ending every part of the engine stops
on; ``rules_ending`` (app/multiplayer/night.py) reads it back as the dummies' win. One dummy left is the ordinary last-player win.

A table without a dummy is never touched.

-- test opponent -- the same holds for opponents the server plays for (app/game/bot.py): once only seats nobody sits in are left (dummies,
opponents, two or more of them), the test is over and they win, recorded with :data:`OPPONENTS_WIN` when an opponent is among them
(an opponent and a dummy would otherwise play on alone, turn after turn).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.game.state import GameState

if TYPE_CHECKING:
    from app.rules.plan import Plan

DUMMIES_WIN = "Only target dummies are left in the game: the dummies win"
OPPONENTS_WIN = "Only the test opponents are left in the game: they win"  # (-- test opponent --)


def _non_human(state: GameState, pid: str) -> bool:
    p = state.players[pid]
    return p.dummy or p.bot is not None


def only_dummies_left(state: GameState) -> list[str] | None:
    """The dummies still in the game when two or more are and nobody else is (else None)."""
    from app.rules.plan import live_players  # (plan imports the engine's modules: late)

    if state.rules is None or not any(p.dummy or p.bot is not None for p in state.players.values()):
        return None
    live = live_players(state)
    if len(live) < 2 or not all(_non_human(state, pid) for pid in live):
        return None
    return live


def end_if_only_dummies(plan: Plan) -> bool:
    """End the game when only target dummies are left in it (two or more). True: it just ended."""
    r = plan.rules
    if r.winner is not None or r.draw_reason is not None:
        return False
    dummies = only_dummies_left(plan.state)
    if dummies is None:
        return False
    bots = any(plan.state.players[pid].bot is not None for pid in dummies)
    r.draw_reason = OPPONENTS_WIN if bots else DUMMIES_WIN
    r.decision = None
    what = "test opponents" if bots else "target dummies"
    plan.note(f"Only {what} are left in the game ({', '.join(plan.name(pid) for pid in dummies)}): the test is over")
    return True


def dummy_winners(state: GameState) -> list[str]:
    """Who won a game :func:`end_if_only_dummies` ended: the dummies still in it."""
    from app.rules.plan import live_players

    r = state.rules
    if r is None or r.draw_reason not in (DUMMIES_WIN, OPPONENTS_WIN):
        return []
    return [pid for pid in live_players(state) if _non_human(state, pid)]
