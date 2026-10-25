"""Wave 110B session 12 (real Oracle text in tests/fixtures/wave110b_cards.json).

* Oblivious Bookworm: 708.2, 708.8 the end-step loot discards unless a permanent entered face down under your control this turn or you turned one face up this turn.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import to_phase
from tests.wave110b_kit import build, card_named, check, drive, mana, put, repository, to_hand


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


@pytest.mark.parametrize("name", ["Oblivious Bookworm"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _bookworm(cards, face_down_this_turn, turn_up_this_turn=False):
    s = build(cards, ["Oblivious Bookworm", "Willbender", "Forest", "Forest", "Forest"], [])
    put(s, "Oblivious Bookworm")
    if turn_up_this_turn:  # cast face down on turn 1, turned up on turn 3
        mana(s, "p1", C=3)
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Willbender").id, face_down=True)
        drive(s)
        to_phase(s, "main1", turn=3)
        mana(s, "p1", U=1, C=1)
        act(s, "p1", type="turn_face_up", card_id=card_named(s, "Willbender").id)
        drive(s)
    elif face_down_this_turn:
        mana(s, "p1", C=3)
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Willbender").id, face_down=True)
        drive(s)
    return s


@pytest.mark.parametrize("face_down, turn_up, discards", [(False, False, 1), (True, False, 0), (False, True, 0)])
def test_oblivious_bookworm_discards_unless_face_down_history(cards, face_down, turn_up, discards):
    s = _bookworm(cards, face_down, turn_up)
    gy = lambda: len(s.state.zones["p1:graveyard"])  # noqa: E731
    before = gy()
    to_phase(s, "main1", turn=s.state.turn.number + 2 if turn_up else 2)
    drive(s)
    assert gy() - before == discards  # (the may-draw was taken in all three cases)
    check(s)
