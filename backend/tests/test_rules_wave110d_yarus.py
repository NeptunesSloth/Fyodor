"""Wave 110D: Yarus, Roar of the Old Gods, real Oracle text (tests/fixtures/wave110d_cards.json).

* 708.9, 110.4: a face-down creature of yours that dies returns face down under its owner's control, then is turned face up (702.37).
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import build, to_hand
from tests.wave110d_kit import card_db, cast_on, check, fresh, full, mana, now, put_new, settle  # noqa: F401


def test_yarus_is_full():
    assert full("Yarus, Roar of the Old Gods")


def test_dead_face_down_creature_returns_face_up(cards):
    s = build(cards, ["Yarus, Roar of the Old Gods", "Scornful Egotist", "Lightning Bolt"])
    put_new(s, "Yarus, Roar of the Old Gods")
    egotist = to_hand(s, "Scornful Egotist", "p1")
    mana(s, "p1", C=3)
    act(s, "p1", type="cast_spell", card_id=egotist.id, face_down=True)
    settle(s)
    assert now(s, egotist).face_down
    cast_on(s, "Lightning Bolt", egotist)
    c = now(s, egotist)
    assert c.zone == "p1:battlefield" and not c.face_down
    check(s)


def test_dead_face_down_instant_stays_in_graveyard(cards):
    """110.4, 708.9: a manifested instant card is not a permanent card, so it cannot return."""
    s = build(cards, ["Yarus, Roar of the Old Gods", "Lightning Bolt", "Lightning Bolt"])
    put_new(s, "Yarus, Roar of the Old Gods")
    bolt = fresh(s, "Lightning Bolt")
    act(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "battlefield"}, face_down=True, face_down_kind="manifest", x=50, y=10)
    assert now(s, bolt).face_down
    cast_on(s, "Lightning Bolt", bolt)
    c = now(s, bolt)
    assert c.zone == "p1:graveyard" and not c.face_down
    check(s)
