"""Wave 110D: Resplendent Marshal, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 603.12, 205.3m, 608.2h: "When this creature enters or dies, you may exile another creature card from your graveyard. When you do, put a +1/+1 counter on
  each creature you control other than this creature that shares a creature type with the exiled card." — only your creatures sharing a type; none otherwise.
"""

from __future__ import annotations

from tests.wave9c_kit import build
from tests.wave110d_kit import card_db, cast_on, check, full, grave_new, now, put_new, settle  # noqa: F401


def test_marshal_is_full():
    assert full("Resplendent Marshal")


def board(cards):
    s = build(cards, ["Resplendent Marshal", "Grizzly Bears", "Grizzly Bears", "Llanowar Elves", "Llanowar Elves", "Murder"] + ["Forest"] * 12, ["Grizzly Bears"] + ["Forest"] * 12)
    return s, put_new(s, "Grizzly Bears"), put_new(s, "Llanowar Elves"), put_new(s, "Grizzly Bears", "p2")


def test_enters_counters_on_creatures_sharing_a_type(cards):
    s, bear, elf, theirs = board(cards)
    exiled = grave_new(s, "Grizzly Bears")
    marshal = cast_on(s, "Resplendent Marshal")
    settle(s)
    assert now(s, exiled).zone == "p1:exile" and now(s, bear).counters.get("+1/+1") == 1
    assert not now(s, elf).counters and not now(s, theirs).counters and not now(s, marshal).counters
    check(s)


def test_dies_trigger_and_nothing_to_exile(cards):
    s, bear, elf, theirs = board(cards)
    marshal = cast_on(s, "Resplendent Marshal")  # (nothing in the graveyard to exile: no counters)
    assert not now(s, bear).counters
    exiled = grave_new(s, "Llanowar Elves")
    cast_on(s, "Murder", marshal)
    settle(s)
    assert now(s, exiled).zone == "p1:exile" and now(s, elf).counters.get("+1/+1") == 1 and not now(s, bear).counters
    check(s)
