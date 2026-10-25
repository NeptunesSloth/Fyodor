"""Wave 110D: The Phasing of Zhalfir, real Oracle text.

* 702.26a, 702.26g: a permanent phased out by chapter I or II is not phased in by its controller's untap step...
* 610.3, 611.2b: ...for as long as you control the Saga; when the Saga leaves, it phases in at its controller's next untap step... (here at once, as the
  duration ends, like the other source-bound phase holds, wave 43).
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave110d_kit import (  # noqa: F401
    build,
    card_db,
    check,
    cost,
    full,
    hand_new,
    mana,
    move,
    now,
    put_new,
    settle,
    to_phase,
)

NAME = "The Phasing of Zhalfir"


def test_full():
    assert full(NAME)


def test_held_out_while_the_saga_stays(cards):
    s = build(cards, [NAME], ["Grizzly Bears"])
    bear = put_new(s, "Grizzly Bears", "p2")
    c = hand_new(s, NAME)
    mana(s, "p1", **cost(NAME))
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s, answers=["1", bear.id])  # (read ahead: start at chapter I, which targets the Bears)
    saga = now(s, c)
    assert now(s, bear).zone == "p2:phased"
    to_phase(s, "main1", turn=2)  # (its controller's untap step passes: it stays out)
    assert now(s, bear).zone == "p2:phased"
    check(s)
    move(s, saga, "graveyard")
    act(s, s.state.rules.priority, type="pass_priority")  # (the duration check runs on the next sync)
    assert now(s, bear).zone == "p2:battlefield"
    check(s)
