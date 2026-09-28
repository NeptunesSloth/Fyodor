"""Who can see which card. The single source of truth for hidden information."""

from __future__ import annotations

from app.game.state import (
    ALL,
    OWNER_VISIBLE_ZONES,
    PUBLIC_ZONES,
    CardInstance,
    GameState,
    split_zone,
)

OMNISCIENT = "__omniscient__"  # local "open table" view (hot-seat goldfishing only)
SPECTATOR = "__spectator__"


def can_see(state: GameState, card: CardInstance, viewer: str) -> bool:
    """True when ``viewer`` may learn this card's identity right now."""
    if viewer == OMNISCIENT:
        return True
    if card.ability is not None:
        return True  # ability objects are always public
    _, zone = split_zone(card.zone)
    if card.revealed or ALL in card.known_to or viewer in card.known_to:
        return True
    if zone in PUBLIC_ZONES:
        if not card.face_down:
            return True
        return viewer == card.controller
    if zone in OWNER_VISIBLE_ZONES and viewer == card.owner:
        return True
    return state.searches.get(viewer) == card.zone


def seers(state: GameState, card: CardInstance) -> set[str]:
    """Every player who can currently see ``card`` (``{ALL}`` when all can)."""
    players = state.seat_order
    who = {p for p in players if can_see(state, card, p)}
    if len(who) == len(players) and _publicly_visible(card):
        return {ALL}
    return who


def _publicly_visible(card: CardInstance) -> bool:
    _, zone = split_zone(card.zone)
    return card.revealed or ALL in card.known_to or (zone in PUBLIC_ZONES and not card.face_down)
