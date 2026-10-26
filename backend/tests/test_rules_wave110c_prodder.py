"""Wave 110C: Sin Prodder: any opponent may have its controller put the revealed card into the graveyard (608.2d: all opponents choose, in turn order); each who did
takes damage equal to its mana value from Sin Prodder (120.3); otherwise the card goes to the hand."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.wave100c_kit import three
from tests.wave110c_kit import check, life, make_db, put, real

PRODDER = ("Menace\nAt the beginning of your upkeep, reveal the top card of your library. Any opponent may have you put that card into your graveyard. If a player does, "
           "this creature deals damage to that player equal to that card's mana value. Otherwise, put that card into your hand.")
EXTRA = [real("Sin Prodder", "{3}{B}", 4, "Creature — Imp", PRODDER, ("3", "3"), "B"),
         real("Five Drop", "{5}", 5, "Artifact", "", None, "")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Sin Prodder")).level == "FULL"


@pytest.mark.parametrize("answers", [(), ("p2",), ("p3",), ("p2", "p3")])
def test_opponents_choose_in_turn_order(cards, answers):
    s = three(cards, ["Sin Prodder", "Five Drop"])
    put(s, "Sin Prodder")
    drop = next(c for c in s.state.cards.values() if c.name == "Five Drop")
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main2")
    act(s, "p1", type="move", card_ids=[drop.id], to={"player": "p1", "zone": "library"}, position="top")
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "choose_one" and s.state.turn.number == 4)
    for who in ("p2", "p3"):
        d = s.state.rules.decision
        assert d is not None and d.player == who
        act(s, who, type="choose", decision_id=d.id, option_ids=["yes" if who in answers else "no"])
    while s.state.rules.stack or s.state.rules.decision:
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[drop.id].zone == ("p1:graveyard" if answers else "p1:hand")
    assert (life(s, "p2"), life(s, "p3")) == tuple(40 - 5 * (p in answers) for p in ("p2", "p3"))
    check(s)
