"""Wave 110C: "Choose X. You may choose the same mode more than once." (700.2d, 601.2b, 107.3a).

* Doomsday Confluence ({X}{X}{B}): exactly X modes, chosen as it is cast, any mode any number of times.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.wave110c_kit import answer, build, card_named, check, make_db, mana, real, to_hand

TEXT = ("Choose X. You may choose the same mode more than once.\n• Each player sacrifices a nonartifact creature of their choice.\n• Create a 3/3 black Dalek "
        "artifact creature token with menace.\n• Each opponent discards a card.")
EXTRA = [real("Doomsday Confluence", "{X}{X}{B}", 1, "Sorcery", TEXT, None, "B")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Doomsday Confluence")).level == "FULL"


def _cast(s, x, modes):
    mana(s, B=1, C=2 * x)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Doomsday Confluence").id, x_value=x, modes=modes)
    answer(s)


def test_x_modes_the_same_mode_twice(cards):
    s = build(cards, ["Doomsday Confluence"], ["Island"])
    _cast(s, 2, [1, 1])
    daleks = [c for c in s.state.cards.values() if c.name == "Dalek" and c.zone == "p1:battlefield"]
    assert len(daleks) == 2
    check(s)


def test_the_number_of_modes_is_x(cards):
    s = build(cards, ["Doomsday Confluence"])
    mana(s, B=1, C=4)
    with pytest.raises(ActionError, match="Choose 2 modes"):
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Doomsday Confluence").id, x_value=2, modes=[1])


def test_x_is_zero_no_modes(cards):
    s = build(cards, ["Doomsday Confluence"])
    _cast(s, 0, [])
    assert card_named(s, "Doomsday Confluence").zone == "p1:graveyard"
    check(s)


def test_different_modes_resolve_in_printed_order(cards):
    s = build(cards, ["Doomsday Confluence"], ["Grizzly Bears", "Island"])
    bears = to_hand(s, "Grizzly Bears", "p2")
    act(s, "p2", type="move", card_ids=[bears.id], to={"player": "p2", "zone": "battlefield"})
    to_hand(s, "Island", "p2")
    hand = len(s.state.zones["p2:hand"])
    _cast(s, 2, [2, 0])
    assert s.state.cards[bears.id].zone == "p2:graveyard" and len(s.state.zones["p2:hand"]) == hand - 1
    check(s)
