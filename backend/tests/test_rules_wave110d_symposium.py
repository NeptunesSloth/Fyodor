"""Wave 110D: Echocasting Symposium, real Oracle text.

* 111.2, 707.2: the target player creates (and controls) a token that is a copy of the target creature, which stays with its controller.
* 702.192a: paradigm exiles the spell as it resolves (tested in wave 50H).
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.wave110d_kit import build, card_db, check, cost, full, hand_new, mana, now, put_new, settle  # noqa: F401

NAME = "Echocasting Symposium"


def test_full():
    assert full(NAME)


@pytest.mark.parametrize("who", ["p1", "p2"])
def test_target_player_gets_a_token_copy_of_the_creature(cards, who):
    s = build(cards, [NAME, "Grizzly Bears"], [])
    bears = put_new(s, "Grizzly Bears")
    c = hand_new(s, NAME)
    mana(s, "p1", **cost(NAME))
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[who, bears.id], target_counts=[1, 1])
    settle(s)
    tokens = [t for t in s.state.cards.values() if t.name == "Grizzly Bears" and t.id != bears.id and t.zone.endswith(":battlefield")]
    assert len(tokens) == 1 and tokens[0].controller == who and now(s, bears).controller == "p1"
    assert now(s, c).zone == "p1:exile"
    check(s)
