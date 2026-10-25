"""Wave 110D: Gift of Doom, real Oracle text (tests/fixtures/wave110d_cards.json).

* 702.37e, 303.4f: "As this Aura is turned face up, you may attach it to a creature." — attached before state-based actions look (704.5m); declining
  leaves an unattached Aura, which goes to the graveyard.
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.wave9c_kit import build, to_hand
from tests.wave110d_kit import card_db, check, full, mana, now, put_new, settle  # noqa: F401


def test_gift_is_full():
    assert full("Gift of Doom")


@pytest.mark.parametrize("attach", [True, False])
def test_turn_up(cards, attach):
    s = build(cards, ["Gift of Doom", "Grizzly Bears", "Grizzly Bears"])
    bears, keep = put_new(s, "Grizzly Bears"), put_new(s, "Grizzly Bears")
    gift = to_hand(s, "Gift of Doom")
    mana(s, "p1", C=3)
    act(s, "p1", type="cast_spell", card_id=gift.id, face_down=True, sources=[])
    settle(s)
    assert now(s, gift).face_down
    act(s, "p1", type="turn_face_up", card_id=gift.id, method="morph")
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears.id])  # (the sacrifice)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[keep.id if attach else "none"])
    assert s.state.rules.decision is None
    if attach:
        assert now(s, gift).zone == "p1:battlefield" and now(s, gift).attached_to == keep.id and not now(s, gift).face_down
    else:
        assert now(s, gift).zone == "p1:graveyard"
    check(s)
