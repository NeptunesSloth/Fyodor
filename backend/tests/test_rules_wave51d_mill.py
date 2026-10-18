"""Wave 51D: a mill sized by the damage dealt, and "If the player mills at least one creature card this way" (CR 2026-09-25), real Oracle text
(tests/fixtures/wave51d_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 701.17a / 603.2c / 608.2c: Anowon, the Ruin Thief - "that player mills a card for each 1 damage dealt to them. If the player mills at least one creature card this way, you
  draw a card." (the cards milled are as many as the damage the trigger is about; a creature card among them, as it is in the graveyard, draws one card).
"""

from __future__ import annotations

from app.game.errors import ActionError  # noqa: F401
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import attack, next_turn, stops
from tests.test_rules_wave51d_if_you_do import cards, drive  # noqa: F401
from tests.wave9c_kit import build, check, put, reloaded

ANOWON = "Anowon, the Ruin Thief"


def test_the_card_is_full(cards):
    assert coverage.of_card_data(cards.resolve(ANOWON)).level == "FULL"


def swing(cards, top):
    s = build(cards, [ANOWON], ["Hill Giant", "Hill Giant"] if top else [], forests=30, islands=30)
    anowon = put(s, ANOWON)
    for name in top * 2:  # (Bob draws the card on top in his draw step: the second one is milled)
        c = next(x for x in s.state.cards.values() if x.name == name and x.owner == "p2" and x.zone == "p2:library")
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "library"}, position="top")
    stops(s)
    next_turn(s)
    hand = len([c for c in s.state.cards.values() if c.zone == "p1:hand"])
    attack(s, anowon)
    drive(s, set())
    return s, hand


def graveyard(s, pid="p2"):
    return [c for c in s.state.cards.values() if c.zone == f"{pid}:graveyard"]


def test_anowon_mills_one_card_per_damage_and_draws_for_a_creature_card(cards):
    s, hand = swing(cards, ["Hill Giant"])
    assert len(graveyard(s)) == 2  # Anowon is a 2/4: two damage, two cards
    assert any(c.name == "Hill Giant" for c in graveyard(s))
    assert len([c for c in s.state.cards.values() if c.zone == "p1:hand"]) == hand + 1
    check(s)
    assert len(graveyard(reloaded(s))) == 2


def test_anowon_draws_nothing_when_no_creature_card_was_milled(cards):
    s, hand = swing(cards, [])
    assert len(graveyard(s)) == 2 and not any("Creature" in s.cards.resolve(c.name)["type_line"] for c in graveyard(s))
    assert len([c for c in s.state.cards.values() if c.zone == "p1:hand"]) == hand
    check(s)
