"""-- test opponent -- the seats nobody sits in: target dummies (app/game/handlers/dummy.py) and opponents the server plays for
(app/game/bot.py). Both act through the server alone, are left out of a table's pod result, and count toward the same limit at a test
table (``MAX_NON_HUMAN``)."""

from __future__ import annotations

from app.game.state import GameState

MAX_NON_HUMAN = 3  # dummies and opponents together, beside the player testing a deck


def is_bot(state: GameState, pid: str | None) -> bool:
    p = state.players.get(pid) if pid else None
    return p is not None and p.bot is not None


def non_human(state: GameState, pid: str | None) -> bool:
    """A target dummy or an opponent the server plays for."""
    p = state.players.get(pid) if pid else None
    return p is not None and (p.dummy or p.bot is not None)


def bots_of(state: GameState) -> list[str]:
    """The table's opponents the server plays for, in seat order (left ones included: callers check)."""
    return [pid for pid in state.seat_order if state.players[pid].bot is not None]


def has_non_human(state: GameState) -> bool:
    return any(p.dummy or p.bot is not None for p in state.players.values())
