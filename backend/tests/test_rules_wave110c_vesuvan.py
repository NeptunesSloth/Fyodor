"""Wave 110C: Vesuvan Shapeshifter (707.5, 614.12a enters as a copy; 702.37e/708.8 turned face up: no "enters" but the "As ... is turned face up" choice; 708.2 the copy lasts
until it is turned face down): the copy has the upkeep ability that turns it face down."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named, to_hand
from tests.wave110c_kit import answer, cast, ch, check, make_db, mana, put, real

TEXT = ('As this creature enters or is turned face up, you may choose another creature on the battlefield. If you do, until this creature is turned face down, it becomes a copy of '
        'that creature, except it has "At the beginning of your upkeep, you may turn this creature face down."\nMorph {1}{U}')
EXTRA = [real("Vesuvan Shapeshifter", "{3}{U}{U}", 5, "Creature — Shapeshifter", TEXT, ("0", "0"), "U"),
         real("Test Ogre", "{3}{R}", 4, "Creature — Ogre", "", ("4", "3"), "R")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Vesuvan Shapeshifter")).level == "FULL"


def view(s):
    c = card_named(s, "Vesuvan Shapeshifter")
    return c, ch(s, s.state.cards[c.id])


def test_enters_as_a_copy_with_the_upkeep_ability(cards):
    s = build(cards, ["Vesuvan Shapeshifter", "Test Ogre"])
    ogre = put(s, "Test Ogre")
    mana(s, U=2, C=3)
    cast(s, "Vesuvan Shapeshifter")
    answer(s, ogre.id)
    me, c = view(s)
    assert me.zone == "p1:battlefield" and c.name == "Test Ogre" and (c.power, c.toughness) == ("4", "3")
    assert any("turn this creature face down" in a.text for a in c.abilities)
    check(s)


def test_declining_enters_as_itself(cards):
    s = build(cards, ["Vesuvan Shapeshifter", "Test Ogre"])
    put(s, "Test Ogre")
    mana(s, U=2, C=3)
    cast(s, "Vesuvan Shapeshifter")
    answer(s, "none")
    assert card_named(s, "Vesuvan Shapeshifter").zone == "p1:graveyard"  # (a 0/0)
    check(s)


def test_turned_face_up_chooses_and_turning_it_face_down_ends_the_copy(cards):
    s = build(cards, ["Vesuvan Shapeshifter", "Test Ogre"])
    ogre = put(s, "Test Ogre")
    vesuvan = to_hand(s, "Vesuvan Shapeshifter")
    act(s, "p1", type="move", card_ids=[vesuvan.id], to={"player": "p1", "zone": "battlefield"}, face_down=True, face_down_kind="morph")
    mana(s, U=1, C=1)
    act(s, "p1", type="turn_face_up", card_id=vesuvan.id)  # morph {1}{U}
    answer(s, ogre.id)
    _, c = view(s)
    assert c.name == "Test Ogre" and (c.power, c.toughness) == ("4", "3")
    act(s, "p1", type="face_down", card_ids=[vesuvan.id], face_down=True)
    act(s, "p1", type="face_down", card_ids=[vesuvan.id], face_down=False)  # (the table tool: no choice is asked)
    _, c = view(s)
    assert c.name == "Vesuvan Shapeshifter" and (c.power, c.toughness) == ("0", "0")
    check(s)
