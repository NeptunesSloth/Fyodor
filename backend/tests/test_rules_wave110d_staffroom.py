"""Wave 110D: Experimental Lab // Staff Room, real Oracle text (tests/fixtures/wave110d_cards.json).

* 700.2, 603.3c: "turn that creature face up or put a +1/+1 counter on it" is a choice of one of the two when a creature deals combat damage to a player.
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.wave9c_kit import build, to_hand
from tests.wave110d_kit import card_db, check, full, mana, next_turn, now, settle, to_phase  # noqa: F401


def test_staff_room_is_full():
    assert full("Experimental Lab // Staff Room")


def _setup(s):
    room = to_hand(s, "Experimental Lab // Staff Room")
    mana(s, "p1", G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=room.id, face=1)
    settle(s)
    slinger = to_hand(s, "Gravel Slinger")
    mana(s, "p1", C=3)
    act(s, "p1", type="cast_spell", card_id=slinger.id, face_down=True, sources=[])
    settle(s)
    s.state.rules.controlled_since[slinger.id].turn = 0
    next_turn(s)
    next_turn(s)
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="set_stops", own=["declare_attackers"], smart_pass=False)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": slinger.id, "target": "p2"}])
    return slinger


@pytest.mark.parametrize("label_part", ["face up", "+1/+1"])
def test_choice(cards, label_part):
    s = build(cards, ["Experimental Lab // Staff Room", "Gravel Slinger"])
    slinger = _setup(s)
    for _ in range(8):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, "p1", type="pass_priority")
    assert d is not None and d.player == "p1"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if label_part in o.label)])
    settle(s)
    c = now(s, slinger)
    assert (not c.face_down and not c.counters) if label_part == "face up" else (c.face_down and c.counters == {"+1/+1": 1})
    check(s)
