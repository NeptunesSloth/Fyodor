"""Wave 110D: Puca's Covenant, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 603.10a, 608.2h: "Whenever a creature you control with a counter on it dies, you may return another target permanent card with mana value less than or equal to the
  number of counters on that creature from your graveyard to your hand. Do this only once each turn." — the counters it had as it died set the limit; a creature
  with no counter does not trigger it.
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110d_kit import card_db, cast_on, check, full, grave_new, now, put, settle  # noqa: F401


def test_puca_is_full():
    assert full("Puca's Covenant")


def test_returns_a_card_up_to_the_counters_it_had(cards):
    s = build(cards, ["Puca's Covenant", "Grizzly Bears", "Llanowar Elves", "Twisted Abomination", "Murder"])
    put(s, "Puca's Covenant")
    bears = put(s, "Grizzly Bears")
    act(s, "p1", type="counter", card_ids=[bears.id], kind="+1/+1", delta=1)
    elves, big = grave_new(s, "Llanowar Elves"), grave_new(s, "Twisted Abomination")
    cast_on(s, "Murder", bears)
    settle(s)
    assert now(s, bears).zone == "p1:graveyard"
    assert now(s, elves).zone == "p1:hand" and now(s, big).zone == "p1:graveyard"
    check(s)


def test_no_counter_no_trigger(cards):
    s = build(cards, ["Puca's Covenant", "Grizzly Bears", "Llanowar Elves", "Murder"])
    put(s, "Puca's Covenant")
    bears = put(s, "Grizzly Bears")
    elves = grave_new(s, "Llanowar Elves")
    cast_on(s, "Murder", bears)
    settle(s)
    assert now(s, elves).zone == "p1:graveyard"
    check(s)
