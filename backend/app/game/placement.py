"""Default battlefield placement for cards played without an explicit drop position."""

from __future__ import annotations

from collections.abc import Mapping

from app.game.state import BATTLEFIELD_H, BATTLEFIELD_W, BattlefieldRow, CardInstance, GameState

CARD_W = 84.0
CARD_H = 100.0
# Rows as fractions of the battlefield height: non-creature spells at the far edge,
# creatures in the middle, lands closest to the player (the client mirrors opponents).
ROWS = {"land": BATTLEFIELD_H * 0.70, "creature": BATTLEFIELD_H * 0.35, "other": BATTLEFIELD_H * 0.03}
# -- saved rows -- a row is its base plus the layers ``free_spot`` stacks over it (5 × 22); a card dropped between two rows
# belongs to the nearer band: the boundaries are halfway between one band's end and the next row's base
_BAND = 5 * 22


def row_for(type_line: str | None) -> str:
    front = (type_line or "").split("//")[0]
    if "Land" in front and "Creature" not in front:
        return "land"
    if "Creature" in front:
        return "creature"
    return "other"


def saved_rows(raw: Mapping[str, str]) -> dict[str, BattlefieldRow]:
    """-- saved rows -- stored rows, checked (a deck's JSON column, a deck id's lookup)."""
    known: dict[str, BattlefieldRow] = {"land": "land", "creature": "creature", "other": "other"}
    return {name: known[row] for name, row in raw.items() if row in known}


def row_at(y: float) -> BattlefieldRow:
    """-- saved rows -- the row a card whose top edge is at ``y`` sits in."""
    if y >= (ROWS["creature"] + _BAND + ROWS["land"]) / 2:
        return "land"
    if y >= (ROWS["other"] + _BAND + ROWS["creature"]) / 2:
        return "creature"
    return "other"


def learns_row(card: CardInstance) -> bool:
    """-- saved rows -- a card of its owner's deck, face up as itself (not a token, copy, test object or merged pile, whose
    names aren't the deck's cards, nor a face-down one, whose name its row must not reveal)."""
    return (bool(card.name) and card.card_id is not None and not card.is_token and card.token is None and card.copy_of is None
            and card.ability is None and not card.test_object and not card.face_down and not card.merged)


def entry_row(state: GameState, pid: str, card: CardInstance, type_line: str | None, *, face_down: bool = False) -> str:
    """-- saved rows -- the row ``card`` enters ``pid``'s battlefield in: the one its owner taught this deck (by moving it there
    by hand, ``PlayerState.row_overrides``) when it enters its owner's own battlefield face up, else its type's row."""
    if card.owner == pid and not face_down and learns_row(card):
        row = state.players[pid].row_overrides.get(card.name) if pid in state.players else None
        if row in ROWS:
            return row
    return row_for(type_line)


def free_spot(state: GameState, zone_key: str, row: str, taken: list[tuple[float, float]] | None = None) -> tuple[float, float]:
    occupied = [(state.cards[cid].x, state.cards[cid].y) for cid in state.zones.get(zone_key, [])]
    occupied += taken or []
    base_y = ROWS[row]
    step = CARD_W + 6
    # -- playtest (nov 16) -- a full row's next layer is laid like bricks, half a card along and a little lower, so each card under it
    # keeps half its face in view: layers nudged 10 along and 44 down landed almost on the card below (the 2D board clamps the low
    # layers of the land row up again), which showed only a ~25 px sliver of it
    for layer in range(6):
        y = base_y + layer * 22
        x = 12.0 + (layer % 2) * step / 2
        while x + CARD_W <= BATTLEFIELD_W:
            if all(abs(ox - x) > CARD_W * 0.6 or abs(oy - y) > CARD_H * 0.15 for ox, oy in occupied):
                return x, y
            x += step
    return 12.0, base_y
