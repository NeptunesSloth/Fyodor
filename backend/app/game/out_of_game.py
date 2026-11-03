"""-- out of the game -- what a player who has left the game may still send.

800.4a: a player who leaves a multiplayer game no longer takes part in it (104.3a: a player who concedes leaves the game
immediately; 104.3 and 704.5a-c: a player who loses leaves it too), and the game goes on without them (800.4). The rules
engine already refuses their rules intents (``app.rules.engine.compile_intent``: "You have left this game"); the table
tools around it would still let them pass the steps and turns, resolve the stack or move cards and life. Those are refused
here, when the action is sent (``GameSession.perform``), never on replay, so a save or an older history still loads.

What stays theirs is what anyone watching at the table does: chat and the table's dice, their own seat's name and look,
stepping aside from a response check (they are never waited on), their rules preferences (the engine decides each rules
intent), and, for the host, the host's table tools (``api.games.HOST_ONLY_ACTIONS``: the API checks who the host is).

Undo, redo and asking the table to undo take back the live game's actions, so they move the game too (``history_refusal``):
refused for a player who is out, except the host, who can still take back a mistaken concession or loss.
"""

from __future__ import annotations

from app.game.actions import INTENT_TYPES
from app.game.state import GameState

OUT_MAY = INTENT_TYPES | frozenset({
    "chat", "roll", "coin", "rename_player", "set_appearance", "end_view", "response_pass", "response_auto",
    "configure", "remove_player", "set_table_playmat", "restart_game", "mulligan_finish",
})


def refusal(state: GameState, actor: str, action_type: str) -> str | None:
    """Why ``actor`` may not send ``action_type`` now (they conceded or lost), or None."""
    return None if action_type in OUT_MAY else reason(state, actor)


def history_refusal(state: GameState, actor: str, *, host: bool) -> str | None:
    """-- out of the game (gaps5) -- Why ``actor`` may not undo, redo or ask the table to undo the live game now (they are out of it), or
    None. ``host``: the host's seat at a LAN table, every seat at a hot-seat one (``GameSession.undo``): the host still may."""
    return None if host else reason(state, actor)


def reason(state: GameState, actor: str) -> str | None:
    """The reason a player who is out is refused (they conceded or lost), or None while they are in the game."""
    r = state.rules
    if r is None:
        return None
    if actor in r.conceded:
        how = "conceded"
    elif actor in r.lost:
        how = "lost"
    else:
        return None
    return f"You're out of this game (you {how}): you can watch and chat, but not move the game."
