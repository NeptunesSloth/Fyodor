"""Wave 52A: mana for the counters an instruction removed (CR 2026-09-25), real Oracle text (tests/fixtures/wave52a_cards.json, from data/cards.sqlite). Every scenario checks
the replay and a save and a load.

* 122.8 / 608.2c / 106.3: Coalition Relic - "At the beginning of your first main phase, remove all charge counters from this artifact. Add one mana of any color for each
  charge counter removed this way." (each mana chosen on its own); Ventifact Bottle - "… if this artifact has a charge counter on it, tap it and remove all charge counters from
  it. Add {C} for each charge counter removed this way."
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act, mana_pool
from tests.test_rules_wave34b_activated import next_turn, settle
from tests.wave9c_kit import build, check, put, zone_of
from tests.wave52a_kit import open_repo

RELIC, BOTTLE, BOUNTY = "Coalition Relic", "Ventifact Bottle", "Bounty of the Luxa"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", [RELIC, BOTTLE, BOUNTY])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def counters(s, c, kind="charge"):
    return s.state.cards[c.id].counters.get(kind, 0)


def test_coalition_relic_adds_a_mana_for_each_charge_counter_it_removed(cards):
    s = build(cards, [RELIC])
    relic = put(s, RELIC)
    act(s, "p1", type="counter", card_ids=[relic.id], kind="charge", delta=3)
    next_turn(s)
    settle(s)  # (the first mana choices are the first color offered)
    assert counters(s, relic) == 0
    assert sum(mana_pool(s).values()) == 3  # one mana of any color for each of the three counters
    check(s)


def test_coalition_relic_without_counters_adds_nothing(cards):
    s = build(cards, [RELIC])
    relic = put(s, RELIC)
    next_turn(s)
    settle(s)
    assert counters(s, relic) == 0 and not mana_pool(s)
    check(s)


def test_ventifact_bottle_taps_and_adds_colorless_for_each_counter(cards):
    s = build(cards, [BOTTLE])
    bottle = put(s, BOTTLE)
    act(s, "p1", type="counter", card_ids=[bottle.id], kind="charge", delta=2)
    next_turn(s)
    settle(s)
    assert counters(s, bottle) == 0 and s.state.cards[bottle.id].tapped
    assert mana_pool(s) == {"C": 2}
    check(s)


def test_ventifact_bottle_with_no_counter_does_nothing(cards):
    s = build(cards, [BOTTLE])
    bottle = put(s, BOTTLE)
    next_turn(s)
    settle(s)
    assert not s.state.cards[bottle.id].tapped and not mana_pool(s) and zone_of(s, BOTTLE) == "p1:battlefield"
    check(s)


# -- Bounty of the Luxa ------------------------------------------------------------------------------------------------------------------
def hand(s):
    return sum(1 for c in s.state.cards.values() if c.zone == "p1:hand")


def test_bounty_of_the_luxa_with_counters_removes_them_and_adds_mana(cards):
    s = build(cards, [BOUNTY])
    b = put(s, BOUNTY)
    act(s, "p1", type="counter", card_ids=[b.id], kind="flood", delta=2)
    next_turn(s)
    settle(s)
    assert counters(s, b, "flood") == 0 and mana_pool(s) == {"C": 1, "G": 1, "U": 1}  # "Otherwise, add {C}{G}{U}": no new counter, no card
    assert hand(s) == 1  # (the draw step's card only)
    check(s)


def test_bounty_of_the_luxa_without_counters_puts_one_on_and_draws(cards):
    s = build(cards, [BOUNTY])
    b = put(s, BOUNTY)
    next_turn(s)
    settle(s)
    assert counters(s, b, "flood") == 1 and not mana_pool(s)
    assert hand(s) == 2  # the draw step's card and the one this draws
    check(s)
