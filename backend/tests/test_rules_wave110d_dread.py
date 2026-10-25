"""Wave 110D: Growing Dread, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 702.37e, 701.40: "Whenever you turn a permanent face up, put a +1/+1 counter on it." — the permanent you turned up gets the counter; a face-down
  permanent still face down, or an opponent's turned up, does not.
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import build, to_hand
from tests.wave110d_kit import card_db, check, full, mana, now, put_new, settle, to_phase  # noqa: F401


def test_growing_dread_is_full():
    assert full("Growing Dread")


def face_down(s, pid="p1"):
    egotist = to_hand(s, "Scornful Egotist", pid)
    mana(s, pid, C=3)
    act(s, pid, type="cast_spell", card_id=egotist.id, face_down=True)
    settle(s)
    assert now(s, egotist).face_down
    return egotist


def test_turned_face_up_gets_counter(cards):
    s = build(cards, ["Growing Dread", "Scornful Egotist"])
    put_new(s, "Growing Dread")
    egotist = face_down(s)
    assert not now(s, egotist).counters
    mana(s, U=1)
    act(s, "p1", type="turn_face_up", card_id=egotist.id)
    settle(s)
    assert not now(s, egotist).face_down and now(s, egotist).counters.get("+1/+1") == 1
    check(s)


def test_opponents_permanent_gets_none(cards):
    s2 = build(cards, ["Growing Dread"], ["Scornful Egotist"])
    put_new(s2, "Growing Dread")
    to_phase(s2, "main1", turn=2)
    egotist = face_down(s2, "p2")
    mana(s2, "p2", U=1)
    act(s2, "p2", type="turn_face_up", card_id=egotist.id)
    settle(s2)
    assert not now(s2, egotist).counters
    check(s2)
