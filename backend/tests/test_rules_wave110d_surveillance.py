"""Wave 110D: Curse of Surveillance, real Oracle text (tests/fixtures/wave110d_cards.json).

* 303.4, 702.5d: at the enchanted player's upkeep, any number of target players other than that player each draw a card per Curse attached to that player.
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave110d_kit import build, card_db, cast_on, check, full, now, settle, to_phase  # noqa: F401


def test_full():
    assert full("Curse of Surveillance")


def test_others_draw_not_the_enchanted_player(cards):
    s = build(cards, ["Curse of Surveillance"])
    curse = cast_on(s, "Curse of Surveillance", "p2")
    assert now(s, curse).attached_player == "p2"
    to_phase(s, "upkeep", turn=2)
    d = s.state.rules.decision
    assert d is not None and "p2" not in [o.id for o in d.options] and "p1" in [o.id for o in d.options]
    mine, theirs = len(s.state.zones["p1:hand"]), len(s.state.zones["p2:hand"])
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["p1"])
    settle(s)
    assert len(s.state.zones["p1:hand"]) == mine + 1 and len(s.state.zones["p2:hand"]) == theirs + 1  # (only its own draw step)
    check(s)
