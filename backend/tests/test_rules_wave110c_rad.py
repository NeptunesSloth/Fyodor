"""Wave 110C: an optional entering choice (614.1c, 614.12a, 122.1j).

* Mariposa Military Base: "You may have this land enter tapped. If you do, you get two rad counters." Asked before it enters; either answer, and the card's second
  line makes its draw ability cheaper for each rad counter."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110c_kit import build, check, make_db, real, to_hand

BASE = ("You may have this land enter tapped. If you do, you get two rad counters.\n{T}: Add {C}.\n"
        "{5}, {T}: Draw a card. This ability costs {1} less to activate for each rad counter you have.")
EXTRA = [real("Mariposa Military Base", "", 0, "Land", BASE, None, "")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Mariposa Military Base")).level == "FULL"


@pytest.mark.parametrize("answer", ["tapped", "no"])
def test_play_land_with_or_without_the_rad_counters(cards, answer):
    s = build(cards, ["Mariposa Military Base"])
    land = to_hand(s, "Mariposa Military Base")
    act(s, "p1", type="play_land", card_id=land.id)
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {"tapped", "no"}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[answer])
    assert s.state.cards[land.id].zone == "p1:battlefield"
    assert s.state.cards[land.id].tapped == (answer == "tapped")
    assert s.state.players["p1"].resources.get("rad", 0) == (2 if answer == "tapped" else 0)
    check(s)
