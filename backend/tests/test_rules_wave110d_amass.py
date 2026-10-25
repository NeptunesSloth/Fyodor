"""Wave 110D: amass reflexive, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 701.47c, 603.12, 115.1, 613.1b: "When Grishnákh enters, amass Orcs 2. When you do, until end of turn, gain control of target nonlegendary
  creature an opponent controls with power less than or equal to the amassed Army's power. Untap that creature. It gains haste until end of turn."
* 118.12, 603.2: "Whenever a player puts a Forest onto the battlefield, this enchantment deals 3 damage to that player unless they put a -1/-1 counter on
  a creature they control." (Tourach's Chant; Thelon's Chant with Swamp) — the land's controller pays or is dealt 3.
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.wave9c_kit import build, life, to_hand
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


def _land(s, name):
    land = to_hand(s, name)
    act(s, "p1", type="play_land", card_id=land.id)
    return land


@pytest.mark.parametrize("chant,land", [("Tourach's Chant", "Forest"), ("Thelon's Chant", "Swamp")])
def test_chant_pays_with_a_counter_or_takes_3(cards, chant, land):
    """Playing the matching basic land: its controller puts a -1/-1 counter on a creature they control, or is dealt 3 damage."""
    s = build(cards, [chant, "Forest", "Swamp", "Grizzly Bears"], ["Mountain"])
    put(s, chant)
    bears = put(s, "Grizzly Bears")
    _land(s, land)
    d = s.state.rules.decision
    assert d is not None and d.player == "p1"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
    settle(s)
    assert life(s, "p1") == 40
    assert now(s, bears).counters.get("-1/-1") == 1
    check(s)


def test_chant_declined_deals_3(cards):
    s = build(cards, ["Tourach's Chant", "Forest"], ["Mountain"])
    put(s, "Tourach's Chant")
    _land(s, "Forest")
    settle(s)
    assert life(s, "p1") == 37
    check(s)


def test_chant_ignores_other_land(cards):
    s = build(cards, ["Tourach's Chant", "Swamp"], ["Mountain"])
    put(s, "Tourach's Chant")
    _land(s, "Swamp")
    settle(s)
    assert life(s, "p1") == 40
    check(s)
