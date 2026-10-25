"""Wave 110D: Growing Dread, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 702.37e, 701.40: "Whenever you turn a permanent face up, put a +1/+1 counter on it." — counts when you turn it (special action or your effect, even on an opponent's permanent); not when an opponent does; not while face down.
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


def test_my_effect_turns_opponents_permanent_up(cards):
    """701.40b, 702.37e: "you turn" is the player who turns it: my Break Open turns the opponent's creature up, so it gets the counter."""
    from tests.wave110d_kit import cast_on

    s = build(cards, ["Growing Dread", "Scornful Egotist", "Break Open"])
    put_new(s, "Growing Dread")
    egotist = face_down(s)
    act(s, "p1", type="set_controller", card_ids=[egotist.id], player="p2")
    cast_on(s, "Break Open", egotist)
    assert not now(s, egotist).face_down and now(s, egotist).counters.get("+1/+1") == 1
    check(s)


def test_opponents_effect_turns_my_permanent_up(cards):
    """The opponent's Break Open turns my creature up: I did not turn it, so no counter."""
    from tests.wave110d_kit import cast_on

    s = build(cards, ["Growing Dread"], ["Scornful Egotist", "Break Open"])
    put_new(s, "Growing Dread")
    to_phase(s, "main1", turn=2)
    egotist = face_down(s, "p2")
    act(s, "p2", type="set_controller", card_ids=[egotist.id], player="p1")
    cast_on(s, "Break Open", egotist, pid="p2")
    assert not now(s, egotist).face_down and not now(s, egotist).counters
    check(s)
