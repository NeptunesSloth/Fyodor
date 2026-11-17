"""-- target dummy -- a test table's game ends once only target dummies are left in it (app/game/dummy.py).

A dummy never plays: it only passes and answers what it's asked. When the last player who isn't a dummy has lost or conceded (or left)
and two or more dummies are still in the game, nothing could ever happen again but the dummies' empty turns, round after round until
their libraries run out. So the game ends there: the dummies win (104.2a gives the one player left the win; with several dummies the
test is simply over). It is recorded as the rules' ``draw_reason`` with :data:`DUMMIES_WIN`, the ending every part of the engine stops
on; ``rules_ending`` (app/multiplayer/night.py) reads it back as the dummies' win. One dummy left is the ordinary last-player win.

A table without a dummy is never touched.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.game.state import GameState

if TYPE_CHECKING:
    from app.rules.plan import Plan

DUMMIES_WIN = "Only target dummies are left in the game: the dummies win"


def only_dummies_left(state: GameState) -> list[str] | None:
    """The dummies still in the game when two or more are and nobody else is (else None)."""
    from app.rules.plan import live_players  # (plan imports the engine's modules: late)

    if state.rules is None or not any(p.dummy for p in state.players.values()):
        return None
    live = live_players(state)
    if len(live) < 2 or not all(state.players[pid].dummy for pid in live):
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
    r.draw_reason = DUMMIES_WIN
    r.decision = None
    plan.note(f"Only target dummies are left in the game ({', '.join(plan.name(pid) for pid in dummies)}): the test is over")
    return True


def dummy_winners(state: GameState) -> list[str]:
    """Who won a game :func:`end_if_only_dummies` ended: the dummies still in it."""
    from app.rules.plan import live_players

    r = state.rules
    if r is None or r.draw_reason != DUMMIES_WIN:
        return []
    return [pid for pid in live_players(state) if state.players[pid].dummy]
