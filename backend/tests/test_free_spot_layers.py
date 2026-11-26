"""-- playtest (nov 16) -- a full row's next cards in the free layout: laid like bricks, never almost on top of the card below."""

from types import SimpleNamespace

from app.game.placement import CARD_W, ROWS, free_spot


def test_a_full_land_row_layers_like_bricks_and_each_card_below_keeps_half_its_face():
    cards: dict[str, SimpleNamespace] = {}
    zone: list[str] = []
    state = SimpleNamespace(cards=cards, zones={"z": zone})
    spots = []
    for i in range(22):
        x, y = free_spot(state, "z", "land")  # type: ignore[arg-type]
        cards[f"c{i}"] = SimpleNamespace(x=x, y=y)
        zone.append(f"c{i}")
        spots.append((x, y))
    first = [s for s in spots if s[1] == ROWS["land"]]
    second = [s for s in spots if s[1] == ROWS["land"] + 22]
    assert len(first) == 11 and second, spots
    # the 12th land lies between two of the first row, half a card along (not 10 units along and 44 down, over one card)
    nearest = min(abs(second[0][0] - x) for x, _ in first)
    assert nearest >= CARD_W / 2 - 1
