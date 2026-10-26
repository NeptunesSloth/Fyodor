"""Wave 110C: Scion of Halaster: 614.11 / 121.6 the first draw event each turn (only while a commander creature you own is out, 614.12) is replaced by look at two,
one to the graveyard, the other back on top, then draw (a new event, 614.5: not replaced again); later draws are plain."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110c_kit import answer, cast, check, gy, make_db, mana, put, real, to_hand

SCION = ('Commander creatures you own have "The first time you would draw a card each turn, instead look at the top two cards of your library. '
         'Put one of them into your graveyard and the other back on top of your library. Then draw a card."')
EXTRA = [real("Scion of Halaster", "{2}{B}", 3, "Creature — Human Wizard", SCION, ("2", "2"), "B"),
         real("Draw Two", "{1}", 1, "Sorcery", "Draw two cards.", None, ""),
         real("Draw One", "{1}", 1, "Sorcery", "Draw a card.", None, "")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Scion of Halaster")).level == "FULL"


def setup(cards, commander):
    from tests.wave9c_kit import build

    s = build(cards, ["Scion of Halaster", "Draw Two", "Draw One"])
    put(s, "Scion of Halaster")
    if commander:
        krenko = next(c for c in s.state.cards.values() if c.owner == "p1" and c.commander_key)
        put(s, krenko.name)
    lib = list(s.state.zones["p1:library"])
    return s, lib


@pytest.mark.parametrize("name,hand_gain,gy_gain", [("Draw Two", 2, 1), ("Draw One", 1, 1)])
def test_first_draw_replaced(cards, name, hand_gain, gy_gain):
    s, lib = setup(cards, True)
    before_hand, before_gy = len(s.state.zones["p1:hand"]), gy(s)
    mana(s, C=1)
    cast(s, name)
    answer(s)
    # spell left the hand (-1) and went to the graveyard (+1)
    assert len(s.state.zones["p1:hand"]) == before_hand + hand_gain
    assert gy(s) == before_gy + 1 + gy_gain
    assert len(s.state.zones["p1:library"]) == len(lib) - 1 - hand_gain - gy_gain  # (1: the spell came out of the library)
    check(s)


def test_second_draw_same_turn_plain(cards):
    s, lib = setup(cards, True)
    two = to_hand(s, "Draw Two")  # (both spells in hand first: the look may mill the other copy)
    one = to_hand(s, "Draw One")
    mana(s, C=2)
    act(s, "p1", type="cast_spell", card_id=one.id)
    answer(s)
    g, h = gy(s), len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=two.id)
    answer(s)
    assert len(s.state.zones["p1:hand"]) == h - 1 + 2  # cast -1, drew 2: no second look
    assert gy(s) == g + 1  # only the spell
    check(s)


def test_no_commander_out_no_replacement(cards):
    s, lib = setup(cards, False)
    mana(s, C=1)
    g = gy(s)
    cast(s, "Draw One")
    answer(s)
    assert gy(s) == g + 1 and len(s.state.zones["p1:library"]) == len(lib) - 2
    check(s)
