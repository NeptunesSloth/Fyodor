"""Wave 110D: Yarus, Roar of the Old Gods, real Oracle text (tests/fixtures/wave110d_cards.json).

* 708.9, 110.4: a face-down creature of yours that dies returns face down under its owner's control, then is turned face up (702.37).
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import build, to_hand
from tests.wave110d_kit import card_db, cast_on, check, full, mana, now, put_new, settle  # noqa: F401


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
