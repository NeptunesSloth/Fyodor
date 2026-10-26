"""Wave 110D: Inventive Iteration // Living Breakthrough, real Oracle text (tests/fixtures/wave110d_cards.json).

* II: "Return an artifact card from your graveyard to your hand. If you can't, draw a card." — a choice, not a target (608.2c); "can't" = none to return (701.21).
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.wave9c_kit import to_hand
from tests.wave110d_kit import (  # noqa: F401
    build,
    card_db,
    check,
    cost,
    full,
    grave_new,
    hand_new,
    mana,
    now,
    settle,
    to_phase,
)

NAME = "Inventive Iteration // Living Breakthrough"


def test_full():
    assert full(NAME)


@pytest.mark.parametrize("artifact", [True, False])
def test_chapter_two(cards, artifact):
    s = build(cards, [NAME, "Sol Ring"])
    ring = grave_new(s, "Sol Ring") if artifact else None
    c = hand_new(s, NAME)
    mana(s, "p1", **cost(NAME))
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    hand = len(s.state.zones["p1:hand"])
    to_phase(s, "main1", turn=3)
    settle(s)
    assert now(s, c).counters.get("lore") == 2
    if artifact:
        assert now(s, ring).zone == "p1:hand"
    else:
        assert len(s.state.zones["p1:hand"]) == hand + 2  # (the turn's draw and chapter II's)
    check(s)


def test_living_breakthrough_same_mana_value(cards):
    """Back face: after a spell of mana value 1, an opponent can't cast mana value 1 spells until my next turn (others stay legal)."""
    from app.game.errors import ActionError

    s = build(cards, [NAME, "Lightning Bolt"], ["Sol Ring", "Grizzly Bears"])
    c = hand_new(s, NAME)
    mana(s, "p1", **cost(NAME))
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s)
    to_phase(s, "main1", turn=5)
    settle(s)
    assert now(s, c).face == 1
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    settle(s)
    ring = to_hand(s, "Sol Ring", "p2")
    bears = to_hand(s, "Grizzly Bears", "p2")
    to_phase(s, "main1", turn=6)
    mana(s, "p2", C=3, G=1)
    with pytest.raises(ActionError):
        act(s, "p2", type="cast_spell", card_id=ring.id)
    act(s, "p2", type="cast_spell", card_id=bears.id)
    settle(s)
    assert now(s, bears).zone == "p2:battlefield"
    check(s)
