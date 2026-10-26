"""Wave 110D: Etrata, Deadly Fugitive, real Oracle text.

* 701.40g, 701.58g, 708.8: the granted "Turn this creature face up. If you can't, exile it, then you may cast the exiled card without paying its mana
  cost." — a face-down creature card turns up; a manifested instant only gets revealed, so it is exiled and may be cast free.
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import build, life, to_hand
from tests.wave110d_kit import activate, card_db, check, fresh, full, mana, now, put_new, settle  # noqa: F401


def test_etrata_is_full():
    assert full("Etrata, Deadly Fugitive")


def _slinger(s):
    slinger = to_hand(s, "Gravel Slinger")
    mana(s, "p1", C=3)
    act(s, "p1", type="cast_spell", card_id=slinger.id, face_down=True, sources=[])
    settle(s)
    return slinger


def test_creature_turns_up(cards):
    s = build(cards, ["Etrata, Deadly Fugitive", "Gravel Slinger"])
    put_new(s, "Etrata, Deadly Fugitive")
    slinger = _slinger(s)
    mana(s, "p1", U=1, B=1, C=2)
    activate(s, slinger, "{2}{U}{B}")
    assert not now(s, slinger).face_down and now(s, slinger).zone == "p1:battlefield"
    check(s)


def test_manifested_instant_is_exiled_and_cast(cards):
    s = build(cards, ["Etrata, Deadly Fugitive", "Lightning Bolt"])
    put_new(s, "Etrata, Deadly Fugitive")
    bolt = fresh(s, "Lightning Bolt")
    act(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "battlefield"}, face_down=True, face_down_kind="manifest", x=50, y=10)
    mana(s, "p1", U=1, B=1, C=2)
    activate(s, bolt, "{2}{U}{B}")
    assert now(s, bolt).zone == "p1:graveyard" and not now(s, bolt).face_down  # cast (the pending prompts were answered by settle), not just exiled
    assert life(s, "p1") + life(s, "p2") == 77
    check(s)
