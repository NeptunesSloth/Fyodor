"""Wave 110D: One with the Kami, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 700.9, 603.10a, 400.7: "Whenever enchanted creature or another modified creature you control dies, create X 1/1 colorless Spirit creature tokens, where X is
  that creature's power." — the enchanted creature and a creature with a counter each make that many Spirits (last known power); a plain creature makes none.
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110d_kit import card_db, cast_on, check, full, put, put_new  # noqa: F401


def test_one_with_the_kami_is_full():
    assert full("One with the Kami")


def _spirits(s):
    return [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Spirit"]


def test_enchanted_creature_dies_makes_spirits_equal_to_power(cards):
    s = build(cards, ["One with the Kami", "Grizzly Bears", "Lightning Bolt"])
    bears = put(s, "Grizzly Bears")
    cast_on(s, "One with the Kami", bears)
    cast_on(s, "Lightning Bolt", bears)
    assert bears.id in s.state.zones["p1:graveyard"] and len(_spirits(s)) == 2
    check(s)


def test_other_modified_creature_dies_but_plain_creature_does_not(cards):
    s = build(cards, ["One with the Kami", "Grizzly Bears", "Grizzly Bears", "Grizzly Bears", "Lightning Bolt", "Lightning Bolt"])
    bears, plain = put_new(s, "Grizzly Bears"), put_new(s, "Grizzly Bears")
    cast_on(s, "One with the Kami", put_new(s, "Grizzly Bears"))  # (the enchanted creature stays alive)
    act(s, "p1", type="counter", card_ids=[bears.id], kind="+1/+1", delta=1)
    cast_on(s, "Lightning Bolt", plain)
    assert not _spirits(s)  # no counter, no Aura: not modified
    cast_on(s, "Lightning Bolt", bears)
    assert len(_spirits(s)) == 3  # power 2 + the counter, last known information
    check(s)
