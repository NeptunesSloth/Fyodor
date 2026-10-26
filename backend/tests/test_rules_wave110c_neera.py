"""Wave 110C: Neera, Wild Mage (601.2, 701.20, 608.2c): the cast spell is put on the bottom of its owner's library (not countered, it never resolves); only if that happened, cards
are revealed until a nonland card, which may be cast free; the rest go to the bottom; the ability triggers once each turn."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named
from tests.wave110c_kit import answer, check, life, make_db, mana, put, real, to_hand

NEERA = ("Whenever you cast a spell, you may put it on the bottom of its owner's library. If you do, reveal cards from the top of your library until you reveal a nonland card. "
         "You may cast that card without paying its mana cost. Then put all revealed cards not cast this way on the bottom of your library in a random order. "
         "This ability triggers only once each turn.")
EXTRA = [real("Neera, Wild Mage", "{1}{U}{R}", 3, "Legendary Creature — Elf Wizard", NEERA, ("2", "2"), "UR")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Neera, Wild Mage")).level == "FULL"


def top(s, *names):
    """Put these cards on top of p1's library, the first name topmost."""
    for n in reversed(names):
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"player": "p1", "zone": "library"}, position="top")


def bolt(s):
    c = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p2"])
    return c


def zone(s, c):
    return s.state.cards[c.id].zone


@pytest.mark.parametrize("take", [True, False])
def test_spell_goes_to_the_bottom_and_a_free_nonland_is_cast(cards, take):
    s = build(cards, ["Neera, Wild Mage", "Lightning Bolt", "Forest", "Grizzly Bears"])
    put(s, "Neera, Wild Mage")
    top(s, "Forest", "Grizzly Bears")
    spell = bolt(s)
    answer(s, "pay" if take else "decline")  # (the free cast offers Grizzly Bears, the first option)
    if take:
        assert zone(s, spell) == "p1:library"
        assert life(s, "p2") == 40
        assert zone(s, card_named(s, "Grizzly Bears")) == "p1:battlefield"
        assert zone(s, card_named(s, "Forest")) == "p1:library"
    else:
        assert life(s, "p2") == 37 and zone(s, spell) == "p1:graveyard"
        assert zone(s, card_named(s, "Grizzly Bears")) == "p1:library"
    check(s)


def test_triggers_once_each_turn(cards):
    s = build(cards, ["Neera, Wild Mage", "Lightning Bolt", "Forest", "Grizzly Bears"])
    put(s, "Neera, Wild Mage")
    top(s, "Grizzly Bears")
    bolt(s)
    answer(s, "decline")
    assert life(s, "p2") == 37
    bolt(s)
    answer(s)
    assert life(s, "p2") == 34  # (no second trigger: nothing asked, the Bolt resolved)
    check(s)
