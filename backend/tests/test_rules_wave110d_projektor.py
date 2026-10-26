"""Wave 110D: Panoptic Projektor, real Oracle text (tests/fixtures/wave110d_cards.json).

* 603.2d, 701.40, 702.37e: "If turning a face-down permanent face up causes a triggered ability of a permanent you control to trigger,
  that ability triggers an additional time." Aphetto Runecaster (any permanent turned face up) draws twice with it, once without; an opponent's
  Runecaster is not a permanent you control, so it is not doubled.
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.wave9c_kit import build, to_hand
from tests.wave110d_kit import card_db, check, full, mana, now, put, put_new, settle  # noqa: F401


def test_full():
    assert full("Panoptic Projektor")


@pytest.mark.parametrize(("who", "projektor", "drawn"), [("p1", True, 2), ("p1", False, 1), ("p2", True, 1)])
def test_runecaster_triggers(cards, who, projektor, drawn):
    s = build(cards, ["Gift of Doom", "Grizzly Bears", "Grizzly Bears", "Aphetto Runecaster", "Panoptic Projektor"],
              ["Aphetto Runecaster"])
    bears, keep = put_new(s, "Grizzly Bears"), put_new(s, "Grizzly Bears")
    put(s, "Aphetto Runecaster", pid=who)
    if projektor:
        put(s, "Panoptic Projektor")
    gift = to_hand(s, "Gift of Doom")
    mana(s, "p1", C=3)
    act(s, "p1", type="cast_spell", card_id=gift.id, face_down=True, sources=[])
    settle(s)
    hand = len(s.state.zones[f"{who}:hand"])
    act(s, "p1", type="turn_face_up", card_id=gift.id, method="morph")
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bears.id])  # (the sacrifice)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[keep.id])  # (the attach)
    settle(s, answers=["yes"] * 4)
    assert len(s.state.zones[f"{who}:hand"]) - hand == drawn
    check(s)
