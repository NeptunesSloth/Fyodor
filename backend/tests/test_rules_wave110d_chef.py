"""Wave 110D: Master Chef, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 614.12, 702.60: "Commander creatures you own have "This creature enters with an additional +1/+1 counter on it" and "Other creatures you control enter with an
  additional +1/+1 counter on them."" — a commander creature entering while Chef is out gets a counter; other creatures enter with one only while you control
  a commander creature (the grant); a creature entering before any commander is out gets none.
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110d_kit import card_db, cast_on, check, full, mana, now, put, settle  # noqa: F401


def test_master_chef_is_full():
    assert full("Master Chef")


def test_commander_and_others_enter_with_counters(cards):
    s = build(cards, ["Master Chef", "Grizzly Bears", "Llanowar Elves"])
    put(s, "Master Chef")
    bears = cast_on(s, "Grizzly Bears")
    assert now(s, bears).counters.get("+1/+1", 0) == 0  # (no commander creature out yet)
    krenko = next(c for c in s.state.cards.values() if c.owner == "p1" and c.commander_key)
    mana(s, R=2, C=2)
    act(s, "p1", type="cast_spell", card_id=krenko.id)
    settle(s)
    assert now(s, krenko).zone == "p1:battlefield" and now(s, krenko).counters.get("+1/+1") == 1
    elves = cast_on(s, "Llanowar Elves")
    assert now(s, elves).counters.get("+1/+1") == 1  # (granted to Krenko: other creatures I control)
    check(s)
