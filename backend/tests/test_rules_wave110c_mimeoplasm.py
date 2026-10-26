"""Wave 110C: The Mimeoplasm (707.5 enters as a copy, 614.12a the choice is made before it enters, 707.9e additional counters only while it enters as that copy,
400.7 the cards leave the graveyards as it enters): the pair is one choice, both cards are exiled and the other one's power is the number of +1/+1 counters."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named
from tests.wave110c_kit import answer, cast, ch, check, make_db, mana, real

TEXT = ("As The Mimeoplasm enters, you may exile two creature cards from graveyards. If you do, it enters as a copy of one of those cards with a number of additional +1/+1 "
        "counters on it equal to the power of the other card.")
EXTRA = [real("The Mimeoplasm", "{2}{G}{U}{B}", 5, "Legendary Creature — Ooze", TEXT, ("0", "0"), "GUB"),
         real("Test Ogre", "{3}{R}", 4, "Creature — Ogre", "", ("4", "3"), "R")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("The Mimeoplasm")).level == "FULL"


def scenario(cards, graveyard):
    s = build(cards, ["The Mimeoplasm", *graveyard])
    for n in graveyard:
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"player": "p1", "zone": "graveyard"})
    mana(s, G=1, U=1, B=1, C=2)
    cast(s, "The Mimeoplasm")
    return s


def test_enters_as_a_copy_of_one_with_counters_from_the_others_power(cards):
    s = scenario(cards, ["Test Ogre", "Grizzly Bears"])
    ogre, bears = card_named(s, "Test Ogre"), card_named(s, "Grizzly Bears")
    answer(s, f"{ogre.id}|{bears.id}")
    me = card_named(s, "The Mimeoplasm")
    c = ch(s, s.state.cards[me.id])
    assert me.zone == "p1:battlefield" and c.name == "Test Ogre" and me.counters.get("+1/+1") == 2 and (c.power, c.toughness) == ("4", "3")
    assert s.state.cards[ogre.id].zone == "p1:exile" and s.state.cards[bears.id].zone == "p1:exile"
    check(s)


def test_declining_enters_as_itself_and_nothing_is_exiled(cards):
    s = scenario(cards, ["Test Ogre", "Grizzly Bears"])
    answer(s, "none")
    assert card_named(s, "Test Ogre").zone == "p1:graveyard" and card_named(s, "Grizzly Bears").zone == "p1:graveyard"
    assert card_named(s, "The Mimeoplasm").zone == "p1:graveyard"  # (a 0/0)
    check(s)


def test_with_one_creature_card_there_is_nothing_to_choose(cards):
    s = scenario(cards, ["Test Ogre"])
    answer(s)
    assert card_named(s, "Test Ogre").zone == "p1:graveyard"
    check(s)
