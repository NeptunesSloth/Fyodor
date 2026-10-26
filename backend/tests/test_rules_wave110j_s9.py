"""Wave 110J session 9: single-card wordings, real Oracle text (tests/fixtures/wave110j_cards.json). Every scenario ends with replay + save/load.

* 613.1b, 608.2d, 701.26: Turf War: the creature's controller gains control of one of the defending player's contested lands (their choice) and untaps it.
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110b_kit import attack
from tests.wave110j_kit import EXTRA, card_db, check, full, now, put_new  # noqa: F401


def test_the_cards_are_full():
    assert full("Turf War")


@pytest.mark.parametrize(("contested", "choice", "taken"), [(0, 0, None), (1, 0, 0), (2, 1, 1)])
def test_turf_war_takes_a_contested_land(cards, contested, choice, taken):
    """The creature's controller (not Turf War's) picks among the lands with contested counters and untaps the one it takes."""
    s = build(cards, ["Turf War", "Grizzly Bears"])
    put_new(s, "Turf War")
    bears = put_new(s, "Grizzly Bears")
    lands = [put_new(s, "Island", "p2") for _ in range(2)]
    for land in lands[:contested]:
        act(s, "p2", type="counter", card_ids=[land.id], kind="contested", delta=1)
    for land in lands:
        act(s, "p2", type="tap", card_ids=[land.id])
    attack(s, bears)
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            assert d.kind == "choose_cards" and d.player == "p1" and len(d.options) == 2
            act(s, "p1", type="choose", decision_id=d.id, option_ids=[lands[choice].id])
        elif s.state.turn.phase == "main2" and not s.state.zones.get("stack"):
            break
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    for i, land in enumerate(lands):
        mine = taken == i
        assert (now(s, land).controller == "p1") is mine and (not now(s, land).tapped) is mine
    check(s)
