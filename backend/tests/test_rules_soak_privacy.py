"""Hidden information found by tools/soak.py: the commander list names each player's commander (903.3, public) but locates it only for a
viewer who may see it. A commander its owner put into their library (903.9b lets them) leaves the library unseen: its zone mustn't tell the
others the moment it is drawn, searched for or put back (400.2), as a face-down one's mustn't say which permanent it is (708.5)."""

from __future__ import annotations

from app.game.visibility import OMNISCIENT, SPECTATOR
from tests.game_helpers import act, find, make_session
from tests.test_rules_effects import replay_matches


def located(s, viewer):
    return next(c for p in s.view(viewer)["players"] if p["id"] == "p1" for c in p["commanders"])["zone"]


def test_a_commander_in_a_hidden_zone_is_not_located_for_others(cards):
    s = make_session(cards, shuffle=True)
    krenko = find(s.state, "Krenko, Mob Boss")
    assert located(s, "p2") == "p1:command"
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "library"})
    act(s, "p1", type="shuffle")
    for _ in range(40):
        act(s, "p1", type="draw", count=1)
        if s.state.cards[krenko.id].zone == "p1:hand":
            break
    assert s.state.cards[krenko.id].zone == "p1:hand"
    assert located(s, "p1") == "p1:hand" and located(s, OMNISCIENT) == "p1:hand"  # its owner (and the host's all-seeing view) still know
    assert located(s, "p2") is None and located(s, SPECTATOR) is None
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"})
    assert located(s, "p2") == "p1:battlefield"  # public again
    replay_matches(s)
