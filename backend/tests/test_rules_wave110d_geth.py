"""Wave 110D: Geth's Summons, real Oracle text (tests/fixtures/wave110d_cards.json).

* 601.2c: a target group for you and one for each opponent with three or more poison counters AS IT IS CAST (Corrupted); each up to one creature card.
* The cards return under your control (400.7, 110.2): your own from your graveyard, the opponent's from theirs.
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.wave110d_kit import (  # noqa: F401
    build,
    card_db,
    check,
    cost,
    full,
    grave_new,
    mana,
    now,
    put_new,
    settle,
    to_hand,
)

NAME = "Geth's Summons"


def test_full():
    assert full(NAME)


def _cast(cards, poison, both=True):
    s = build(cards, [NAME, "Hill Giant"], ["Grizzly Bears"])
    mine = grave_new(s, "Hill Giant")
    theirs = grave_new(s, "Grizzly Bears", "p2")
    act(s, "p2", type="set_resource", player="p2", key="poison", value=poison)
    mana(s, "p1", **cost(NAME))
    c = to_hand(s, NAME)
    return s, c, mine, theirs


def _targets(s):
    d = s.state.rules.decision
    return d


@pytest.mark.parametrize(("poison", "gets_theirs"), [(3, True), (9, True), (2, False), (0, False)])
def test_corrupted_needs_three_poison_counters(cards, poison, gets_theirs):
    s, c, mine, theirs = _cast(cards, poison)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[mine.id, theirs.id] if gets_theirs else [mine.id], target_counts=[1, 1] if gets_theirs else [1])
    settle(s)
    assert now(s, mine).zone == "p1:battlefield" and now(s, mine).controller == "p1"
    if gets_theirs:
        assert now(s, theirs).controller == "p1"  # under your control
    else:
        assert now(s, theirs).zone == "p2:graveyard"
    check(s)


def test_an_opponent_without_poison_offers_no_target(cards):
    from app.game.errors import ActionError

    s, c, mine, theirs = _cast(cards, 2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=c.id, targets=[mine.id, theirs.id], target_counts=[1, 1])


def test_only_the_poisoned_opponent_of_three_gets_a_group(cards):
    from tests.wave47b_kit import build3

    s = build3(cards, [NAME, "Hill Giant"], ["Grizzly Bears"], ["Grizzly Bears"])
    mine, bob, carol = (next(c for c in s.state.cards.values() if c.name == n and c.owner == o and c.zone == f"{o}:library")
                        for n, o in (("Hill Giant", "p1"), ("Grizzly Bears", "p2"), ("Grizzly Bears", "p3")))
    for c in (mine, bob, carol):
        act(s, c.owner, type="move", card_ids=[c.id], to={"zone": "graveyard"})
    act(s, "p3", type="set_resource", player="p3", key="poison", value=4)
    mana(s, "p1", **cost(NAME))
    act(s, "p1", type="cast_spell", card_id=to_hand(s, NAME).id, targets=[mine.id, carol.id], target_counts=[1, 1])
    settle(s)
    assert (now(s, mine).zone, now(s, carol).zone, now(s, bob).zone) == ("p1:battlefield", "p1:battlefield", "p2:graveyard")
    assert now(s, carol).controller == "p1"
    check(s)
