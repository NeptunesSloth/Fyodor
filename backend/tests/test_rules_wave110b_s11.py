"""Wave 110B session 11: single cards read from an exact wording (real Oracle text in tests/fixtures/wave110b_cards.json).

* Scholarship Sponsor: 701.23, 101.4 each player with fewer lands than the most searches for up to the difference in basic lands, tapped.
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


@pytest.mark.parametrize("name", ["Mirror of Life Trapping", "Scholarship Sponsor"])
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


def _land(s, pid, name):
    """A different card of that name from the library each call (put() returns the same one)."""
    cid = next(c for c in s.state.zones[f"{pid}:library"] if s.state.cards[c].name == name)
    act(s, pid, type="move", card_ids=[cid], to={"player": pid, "zone": "battlefield"})


def _lands(s, pid):
    return [c for c in s.state.cards.values() if c.controller == pid and c.zone.endswith(":battlefield") and c.name in ("Forest", "Island")]


@pytest.mark.parametrize("mine, theirs, gain_p1, gain_p2", [(0, 3, 3, 0), (4, 1, 0, 3), (2, 2, 0, 0), (1, 2, 1, 0)])
def test_scholarship_sponsor_fetches_the_land_difference_for_each_trailing_player(cards, mine, theirs, gain_p1, gain_p2):
    s = build(cards, ["Scholarship Sponsor"], [], forests=40, islands=40)
    for _ in range(mine):
        _land(s, "p1", "Forest")
    for _ in range(theirs):
        _land(s, "p2", "Island")
    before = len(_lands(s, "p1")), len(_lands(s, "p2"))
    mana(s, "p1", W=1, C=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Scholarship Sponsor").id)
    drive(s, lambda d: [o.id for o in d.options][: d.max_choices])
    assert len(_lands(s, "p1")) - before[0] == gain_p1
    assert len(_lands(s, "p2")) - before[1] == gain_p2
    assert all(c.tapped for c in _lands(s, "p1")[mine:]) and all(c.tapped for c in _lands(s, "p2")[theirs:])
    check(s)
