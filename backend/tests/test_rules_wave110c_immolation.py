"""Wave 110C: Soul Immolation (701.68a blight X as an additional cost, 107.3a/601.2b X announced, capped by the greatest toughness among your creatures; X damage to each opponent and each creature they control)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110c_kit import answer, build, check, make_db, mana, put, real, to_hand

TEXT = ("As an additional cost to cast this spell, blight X. X can't be greater than the greatest toughness among creatures you control. (Put X -1/-1 counters on a creature you control.)\n"
        "Soul Immolation deals X damage to each opponent and each creature they control.")
EXTRA = [real("Soul Immolation", "{1}{R}{R}", 3, "Sorcery", TEXT, None, "R")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Soul Immolation")).level == "FULL"


def _cast(cards, x):
    s = build(cards, ["Soul Immolation", "Grizzly Bears"], ["Courser of Kruphix", "Grizzly Bears"])
    mine = put(s, "Grizzly Bears")  # 2/2
    theirs = put(s, "Courser of Kruphix", "p2")  # 2/4
    bears2 = put(s, "Grizzly Bears", "p2")  # 2/2
    c = to_hand(s, "Soul Immolation")
    mana(s, R=3)
    return s, c, mine, theirs, bears2


def test_x_counters_on_my_creature_and_x_damage_to_them(cards):
    s, c, mine, theirs, bears2 = _cast(cards, 2)
    life = s.state.players["p2"].life
    act(s, "p1", type="cast_spell", card_id=c.id, x_value=2, cost_choices=[{"component": 0, "cards": [mine.id]}])
    answer(s)
    assert s.state.cards[mine.id].zone == "p1:graveyard"  # two -1/-1 counters on a 2/2 (704.5f)
    assert s.state.cards[bears2.id].zone == "p2:graveyard"
    assert s.state.cards[theirs.id].zone == "p2:battlefield" and s.state.cards[theirs.id].damage == 2
    assert s.state.players["p2"].life == life - 2
    check(s)


def test_x_above_greatest_toughness_refused(cards):
    s, c, mine, *_ = _cast(cards, 3)
    with pytest.raises(Exception, match="greatest toughness"):
        act(s, "p1", type="cast_spell", card_id=c.id, x_value=3, cost_choices=[{"component": 0, "cards": [mine.id]}])


def test_x_one_leaves_a_counter_and_deals_one(cards):
    s, c, mine, theirs, bears2 = _cast(cards, 1)
    act(s, "p1", type="cast_spell", card_id=c.id, x_value=1, cost_choices=[{"component": 0, "cards": [mine.id]}])
    answer(s)
    assert s.state.cards[mine.id].counters.get("-1/-1") == 1 and s.state.cards[bears2.id].damage == 1
    check(s)
