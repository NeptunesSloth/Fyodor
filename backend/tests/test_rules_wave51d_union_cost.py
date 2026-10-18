"""Wave 51D: "X card or Y card" read as one selector (CR 2026-09-25), real Oracle text (tests/fixtures/wave51d_cards.json, from data/cards.sqlite). Every scenario checks the replay
and a save and a load.

* 205.2 / 601.2h: Sanctum of Shattered Heights - "{1}, Discard a land card or Shrine card: … deals X damage to target creature or planeswalker, where X is the number of
  Shrines you control." The discard is of a land card, or of a Shrine card (which is not a land); any other card cannot pay it.
* 205.2: a supertype in front ("basic land card or Cave card") stays unread: it would narrow the Cave too (the selector's is one list).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage, selectors
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, settle
from tests.test_rules_wave51d_if_you_do import cards  # noqa: F401
from tests.wave9c_kit import build, card_named, check, mana, put, reloaded, to_hand, zone_of

SANCTUM = "Sanctum of Shattered Heights"


def test_the_card_is_full(cards):
    assert coverage.of_card_data(cards.resolve(SANCTUM)).level == "FULL"


def test_the_card_or_card_selector_is_one_union_and_a_supertype_in_front_is_left_alone():
    union = selectors.parse("land card or Shrine card")
    assert union is not None and union.union and union.types == ("Land",) and union.subtypes == ("Shrine",)
    assert selectors.parse("basic land card or Cave card") is None


def table(cards, hand):
    s = build(cards, [SANCTUM, "Hill Giant", *hand], ["Hill Giant"], forests=30)
    sanctum = put(s, SANCTUM)
    giant = put(s, "Hill Giant", "p2")
    for name in hand:
        to_hand(s, name)
    mana(s, "p1", G=1)
    return s, sanctum, giant


def test_a_land_card_is_discarded_to_hurt_a_creature_for_each_shrine(cards):
    s, sanctum, giant = table(cards, ["Forest"])
    forest = next(c for c in s.state.cards.values() if c.zone == "p1:hand" and c.name == "Forest")
    activate(s, "p1", sanctum, targets=[giant.id])
    settle(s)
    for _ in range(5):
        d = s.state.rules.decision
        if d is None:
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[forest.id])
        settle(s)
    assert zone_of(s, "Forest") == "p1:graveyard" and s.state.cards[giant.id].damage == 1  # one Shrine: Sanctum itself
    check(s)
    assert reloaded(s).state.cards[giant.id].damage == 1


def test_a_nonland_nonshrine_card_cannot_pay_the_discard(cards):
    s, sanctum, giant = table(cards, [])
    bears = to_hand(s, "Hill Giant")  # a creature card: neither a land card nor a Shrine card
    mana(s, "p1", G=1)
    with pytest.raises(ActionError):
        activate(s, "p1", sanctum, targets=[giant.id])
    assert zone_of(s, "Hill Giant") == "p1:hand" and s.state.cards[giant.id].damage == 0 and card_named(s, SANCTUM).tapped is False
    check(s)
