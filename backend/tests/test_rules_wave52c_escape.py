"""Wave 52C: an instant's or sorcery's printed escape (CR 702.138a, 702.138b), real Oracle text (tests/fixtures/wave52c_cards.json, from data/cards.sqlite). Every scenario checks the
replay and a save and a load.

* 702.138a: "Escape—[cost], Exile N other cards from your graveyard" lets the card be cast from its owner's graveyard for that alternative cost; escape does not exile an
  instant or sorcery (only 702.138c's permanents "escape with" counters), so it goes back to the graveyard as it resolves.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named, check, mana, to_hand, zone_of
from tests.wave52c_kit import castable, drive, move, open_repo

GLIMPSE, CLING, SATYR, SWEET = "Glimpse of Freedom", "Cling to Dust", "Satyr's Cunning", "Sweet Oblivion"
OTHERS = ["Run for Your Life", "Sleep of the Dead", "Fruit of Tizerus"]
FILLER = ["Grizzly Bears", "Llanowar Elves", "Frogmite", "Opt", "Giant Growth"]


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", [GLIMPSE, CLING, SATYR, SWEET, *OTHERS])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_glimpse_of_freedom_escapes_and_goes_back_to_the_graveyard(cards):
    s = build(cards, [GLIMPSE, *FILLER])
    glimpse = move(s, GLIMPSE, "graveyard")
    for name in FILLER[:4]:
        move(s, name, "graveyard")
    mana(s, U=3)
    assert not castable(s, glimpse)  # (four other cards: five are needed)
    move(s, FILLER[4], "graveyard")
    assert castable(s, glimpse)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=glimpse.id)
    drive(s)
    assert len(s.state.zones["p1:hand"]) == hand + 1  # draw a card
    assert zone_of(s, GLIMPSE) == "p1:graveyard"  # (an escaped instant is not exiled: 702.138a)
    assert len(s.state.zones["p1:exile"]) == 5
    check(s)


def test_it_is_cast_from_the_hand_for_its_mana_cost_without_exiling(cards):
    s = build(cards, [GLIMPSE, *FILLER])
    to_hand(s, GLIMPSE)
    mana(s, U=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, GLIMPSE).id)
    drive(s)
    assert zone_of(s, GLIMPSE) == "p1:graveyard" and not s.state.zones["p1:exile"]
    check(s)
