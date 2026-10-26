"""Wave 110C: Yidaro, Wandering Monster: 702.29a-c "When you cycle this card" -- the card is in the graveyard when the trigger resolves; it is shuffled into the
library, or (the fourth time a card with its name was cycled this game, counting this one) put onto the battlefield from the graveyard instead."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave7b_activation import ability_index
from tests.wave110c_kit import answer, check, make_db, mana, real

YIDARO = ("Trample, haste\nCycling {1}{R}\nWhen you cycle this card, shuffle it into your library from your graveyard. If you've cycled a card named Yidaro, "
          "Wandering Monster four or more times this game, put it onto the battlefield from your graveyard instead. (Do this before you draw.)")
EXTRA = [real("Yidaro, Wandering Monster", "{3}{R}{R}", 5, "Legendary Creature — Cyclops", YIDARO, ("6", "5"), "R")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Yidaro, Wandering Monster")).level == "FULL"


def test_fourth_cycling_returns_it(cards):
    from tests.wave9c_kit import build, card_named

    s = build(cards, ["Yidaro, Wandering Monster"])
    y = card_named(s, "Yidaro, Wandering Monster")
    for n in range(1, 5):
        act(s, "p1", type="move", card_ids=[y.id], to={"player": "p1", "zone": "hand"})
        mana(s, R=1, C=1)
        act(s, "p1", type="activate_ability", card_id=y.id, ability=ability_index(s, s.state.cards[y.id], "Cycling"))
        answer(s)
        # (shuffled in before the draw, so the draw may take it right back: library or hand)
        assert (s.state.cards[y.id].zone == "p1:battlefield") if n == 4 else s.state.cards[y.id].zone in ("p1:library", "p1:hand"), n
    check(s)
