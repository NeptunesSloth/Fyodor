"""Wave 110B session 11: single cards read from an exact wording (real Oracle text in tests/fixtures/wave110b_cards.json).

* Mirror of Life Trapping: 607.2a linked exile; a cast creature is exiled as it enters and every other permanent card exiled with it returns (400.7).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import to_phase
from tests.wave110b_kit import build, card_named, check, drive, mana, put, repository, to_hand


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


@pytest.mark.parametrize("name", ["Mirror of Life Trapping"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_mirror_of_life_trapping_exiles_cast_creatures_and_returns_the_others(cards):
    s = build(cards, ["Mirror of Life Trapping", "Grizzly Bears", "Shivan Dragon"], [])
    put(s, "Mirror of Life Trapping")
    bears = card_named(s, "Grizzly Bears")
    to_phase(s, "main1", turn=3)
    mana(s, "p1", G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Grizzly Bears").id)
    drive(s)
    assert s.state.cards[bears.id].zone == "p1:exile"
    mana(s, "p1", R=2, C=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Shivan Dragon").id)
    drive(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield"
    assert s.state.cards[card_named(s, "Shivan Dragon").id].zone == "p1:exile"
    check(s)


def test_mirror_of_life_trapping_ignores_creatures_that_were_not_cast(cards):
    s = build(cards, ["Mirror of Life Trapping", "Grizzly Bears"], [])
    put(s, "Mirror of Life Trapping")
    put(s, "Grizzly Bears")
    assert s.state.cards[card_named(s, "Grizzly Bears").id].zone == "p1:battlefield"
    check(s)
