"""Who can see which card *right now*. The single source of truth for hidden information.

Visibility is computed from current facts only:

* PUBLIC      face-up cards in public zones (battlefield, graveyard, exile, command, stack)
* OWNER       cards in the owner's hand, sideboard and foretell (face-down exile) zones
* CONTROLLER  face-down cards on the battlefield/stack/exile
* REVEALED    an active reveal to everyone or to selected players (``revealed_to``)
* VIEWING     an open search / look-at-top-N context (``state.views``)
* HIDDEN      everything else, e.g. a library

There is no memory of past sightings: a card that was public and moves into a hand is
anonymous to opponents from then on. Historical log lines are separate (``LogPart``).
"""

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
    if viewer == OMNISCIENT or card.ability is not None:
        return True
    if ALL in card.revealed_to or viewer in card.revealed_to:
        return True
    _, zone = split_zone(card.zone)
    if zone in PUBLIC_ZONES:
        return not card.face_down or viewer == card.controller
    if zone in OWNER_VISIBLE_ZONES and viewer == card.owner:
        return True
    for view in state.views:
        if view.viewer == viewer and view.zone == card.zone and (view.kind == "search" or card.id in view.card_ids):
            return True
    return False


def publicly_visible(state: GameState, card: CardInstance) -> bool:
    """Visible to everyone, including spectators."""
    if card.ability is not None or ALL in card.revealed_to:
        return True
    _, zone = split_zone(card.zone)
    return zone in PUBLIC_ZONES and not card.face_down


def seers(state: GameState, card: CardInstance) -> set[str]:
    """Players who can currently see ``card`` (``{ALL}`` when it is public). Used for log lines."""
    if publicly_visible(state, card):
        return {ALL}
    return {p for p in state.seat_order if can_see(state, card, p)}
