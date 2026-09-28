"""Default battlefield placement for cards played without an explicit drop position."""

from __future__ import annotations

from app.game.state import BATTLEFIELD_H, BATTLEFIELD_W, GameState

CARD_W = 84.0
CARD_H = 100.0
# Rows as fractions of the battlefield height: non-creature spells at the far edge,
# creatures in the middle, lands closest to the player (the client mirrors opponents).
ROWS = {"land": BATTLEFIELD_H * 0.70, "creature": BATTLEFIELD_H * 0.35, "other": BATTLEFIELD_H * 0.03}


def row_for(type_line: str | None) -> str:
    front = (type_line or "").split("//")[0]
    if "Land" in front and "Creature" not in front:
        return "land"
    if "Creature" in front:
        return "creature"
    return "other"


def free_spot(state: GameState, zone_key: str, row: str, taken: list[tuple[float, float]] | None = None) -> tuple[float, float]:
    occupied = [(state.cards[cid].x, state.cards[cid].y) for cid in state.zones.get(zone_key, [])]
    occupied += taken or []
    base_y = ROWS[row]
    step = CARD_W + 6
    for layer in range(6):
        y = base_y + layer * 22
        x = 12.0 + layer * 10
        while x + CARD_W <= BATTLEFIELD_W:
            if all(abs(ox - x) > CARD_W * 0.6 or abs(oy - y) > CARD_H * 0.3 for ox, oy in occupied):
                return x, y
            x += step
    return 12.0, base_y
