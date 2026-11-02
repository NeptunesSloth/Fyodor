"""Small public summaries of a table, for the Play page's tiles (tables in progress, saved games)."""

from __future__ import annotations

from typing import Any

from app.game.state import GameState


def player_commanders(state: GameState, pid: str) -> list[dict[str, Any]]:
    """A player's commanders (name and printing, for art), in deck order. Public once the game has started: every commander
    begins the game face up in the command zone (903.6), so naming them reveals nothing a player at the table can't see."""
    found = sorted((c.commander_key, c) for c in state.cards.values() if c.commander_key and c.owner == pid)
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for key, card in found:
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": card.name, "card_id": card.card_id})
    return out
