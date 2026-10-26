"""Wave 110C: Retriever Phoenix. 701.48a (Learn: discard to draw; no Lesson import in Commander, 903.11), 614.1 / 616.1 (the controller's replacement
"if you would learn ... instead return this card to the battlefield", only while the card is in the graveyard), 400.7 (a new object)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.wave110c_kit import answer, build, card_named, cast, check, make_db, mana, put, real, zone

PHOENIX = ("Flying, haste\nWhen this creature enters, if you cast it, learn. (You may reveal a Lesson card you own from outside the game and put it into "
           "your hand, or discard a card to draw a card.)\nAs long as this card is in your graveyard, if you would learn, you may instead return this "
           "card to the battlefield.")
EXTRA = [real("Retriever Phoenix", "{2}{R}", 3, "Creature — Phoenix", PHOENIX, ("2", "2"), "R"),
         real("Test Learner", "{G}", 1, "Creature — Student", "When this creature enters, learn.", ("1", "1"), "G"),
         real("Test Fodder", "{G}", 1, "Creature — Bear", "", ("1", "1"), "G")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Retriever Phoenix")).level == "FULL"


def _graveyard(s, name):
    c = card_named(s, name)
    from tests.game_helpers import act

    act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "graveyard"})
    return c


def test_replacement_returns_the_phoenix_instead_of_learning(cards):
    s = build(cards, ["Retriever Phoenix", "Test Learner", "Test Fodder"])
    phoenix = _graveyard(s, "Retriever Phoenix")
    mana(s, G=1)
    cast(s, "Test Learner")
    answer(s, phoenix.id)
    assert zone(s, phoenix) == "p1:battlefield"
    check(s)


def test_declining_learns_normally(cards):  # discard Fodder, draw a card
    s = build(cards, ["Retriever Phoenix", "Test Learner", "Test Fodder"])
    _graveyard(s, "Retriever Phoenix")
    fodder = card_named(s, "Test Fodder")
    from tests.game_helpers import act

    act(s, "p1", type="move", card_ids=[fodder.id], to={"zone": "hand"})
    mana(s, G=1)
    cast(s, "Test Learner")
    hand = len(s.state.zones["p1:hand"])
    answer(s, "learn")
    assert zone(s, fodder) == "p1:graveyard" and len(s.state.zones["p1:hand"]) == hand
    check(s)


def test_no_phoenix_in_graveyard_is_the_plain_learn(cards):
    s = build(cards, ["Retriever Phoenix", "Test Learner", "Test Fodder"])
    fodder = card_named(s, "Test Fodder")
    from tests.game_helpers import act

    act(s, "p1", type="move", card_ids=[fodder.id], to={"zone": "hand"})
    mana(s, G=1)
    cast(s, "Test Learner")
    answer(s)
    assert zone(s, fodder) == "p1:graveyard"
    assert zone(s, card_named(s, "Retriever Phoenix")) == "p1:hand"  # the card drawn


def test_phoenix_on_the_battlefield_does_not_replace(cards):
    s = build(cards, ["Retriever Phoenix", "Test Learner"])
    put(s, "Retriever Phoenix")
    mana(s, G=1)
    cast(s, "Test Learner")
    answer(s)
    assert zone(s, card_named(s, "Retriever Phoenix")) == "p1:battlefield"
