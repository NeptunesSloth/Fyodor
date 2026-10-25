"""Wave 110D: amass reflexive, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 701.47c, 603.12, 115.1, 613.1b: "When Grishnákh enters, amass Orcs 2. When you do, until end of turn, gain control of target nonlegendary
  creature an opponent controls with power less than or equal to the amassed Army's power. Untap that creature. It gains haste until end of turn."
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import build, to_hand
from tests.wave110d_kit import card_db, check, full, mana, now, put, settle  # noqa: F401


def test_grishnakh_is_full():
    assert full("Grishnákh, Brash Instigator")


def _cast(s):
    gr = to_hand(s, "Grishnákh, Brash Instigator")
    mana(s, B=1, C=1, R=1)
    act(s, "p1", type="cast_spell", card_id=gr.id)
    settle(s)


def test_grishnakh_steals_only_creature_within_army_power(cards):
    """The Army has two +1/+1 counters: power 2. Grizzly Bears (2) is the only legal target; Twisted Abomination (5) stays."""
    s = build(cards, ["Grishnákh, Brash Instigator"], ["Grizzly Bears", "Twisted Abomination"])
    bears, big = put(s, "Grizzly Bears", "p2"), put(s, "Twisted Abomination", "p2")
    act(s, "p2", type="tap", card_ids=[bears.id])
    _cast(s)
    assert now(s, bears).controller == "p1" and not now(s, bears).tapped
    assert now(s, big).controller == "p2"
    army = next(c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Orc Army")
    assert army.counters == {"+1/+1": 2}
    check(s)


def test_grishnakh_too_strong_target_not_stolen(cards):
    s = build(cards, ["Grishnákh, Brash Instigator"], ["Twisted Abomination"])
    big = put(s, "Twisted Abomination", "p2")
    _cast(s)
    assert now(s, big).controller == "p2"
    check(s)
