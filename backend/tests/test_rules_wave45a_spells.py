"""Wave 45A: spells one wording short of FULL (CR 2026-09-25), real Oracle text (tests/fixtures/wave45a_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load. The attack-damage cards are in test_rules_wave45a_attacked.py.

* 701.10b, 613.4c: "Until end of turn, double target creature's power and it gains first strike." (Legion Leadership [1222], front face) - +X/+0 where X is its power
  as the spell resolves, and the one creature gains first strike until end of turn.
* 115.1: "Return target Dragon creature card or Ugin planeswalker card from your graveyard to your hand." (Haven of the Spirit Dragon [1141]) - two kinds of card, each its
  own qualifier, in one zone.
* 701.10d, 119.5: "Double target player's life total." (Beacon of Immortality [2919]), "Double your life total." (Revenge, the back of Revival) - the player gains (or, from a
  negative total, loses) what it takes to reach twice the total: a life gain event, so its triggers and replacements apply (Beacon's ruling 2007-07-15).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, settle
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand, zone_of
from tests.wave45a_kit import FULL, cast, life, open_cards


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def keywords(s, name, pid="p1"):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name, pid).id]).keywords


# ---- Legion Leadership [1222] ----------------------------------------------------------------------------------------------------------------------------
def test_legion_leadership_doubles_the_power_and_grants_first_strike_until_end_of_turn(cards):
    s = build(cards, ["Legion Leadership // Legion Stronghold", "Hill Giant"], [])
    giant = put(s, "Hill Giant")
    to_hand(s, "Legion Leadership // Legion Stronghold")
    mana(s, R=1, W=1, C=2)
    assert pt(s, "Hill Giant") == (3, 3) and "first strike" not in keywords(s, "Hill Giant")
    cast(s, "Legion Leadership // Legion Stronghold", targets=[giant.id], face=0)
    assert pt(s, "Hill Giant") == (6, 3)  # 701.10b: +3/+0 (its power as the spell resolved)
    assert "first strike" in keywords(s, "Hill Giant")
    check(s)


def test_legion_leadership_needs_a_target(cards):
    from app.game.errors import ActionError

    s = build(cards, ["Legion Leadership // Legion Stronghold"], [])
    to_hand(s, "Legion Leadership // Legion Stronghold")
    mana(s, R=1, W=1, C=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Legion Leadership // Legion Stronghold").id, face=0)  # 601.2c: a target is required
    check(s)


# ---- Beacon of Immortality [2919] ------------------------------------------------------------------------------------------------------------------------
def test_beacon_of_immortality_doubles_a_players_life_total_and_is_shuffled_into_its_owners_library(cards):
    s = build(cards, ["Beacon of Immortality"], [])
    to_hand(s, "Beacon of Immortality")
    act(s, "p2", type="life", delta=-15)  # Bob: 25
    mana(s, W=1, C=5)
    cast(s, "Beacon of Immortality", targets=["p2"])
    assert life(s, "p2") == 50 and life(s, "p1") == 40
    assert zone_of(s, "Beacon of Immortality") == "p1:library"  # (the second sentence: shuffled back, not put into the graveyard)
    check(s)


def test_beacon_of_immortality_on_yourself(cards):
    s = build(cards, ["Beacon of Immortality"], [])
    to_hand(s, "Beacon of Immortality")
    act(s, "p1", type="life", delta=-15)
    mana(s, W=1, C=5)
    cast(s, "Beacon of Immortality", targets=["p1"])
    assert life(s, "p1") == 50 and life(s, "p2") == 40
    check(s)


# ---- Revival // Revenge ----------------------------------------------------------------------------------------------------------------------------------
def test_revenge_doubles_your_life_total_and_makes_an_opponent_lose_half_theirs(cards):
    s = build(cards, ["Revival // Revenge"], [])
    to_hand(s, "Revival // Revenge")
    act(s, "p1", type="life", delta=-10)  # Alice: 30
    mana(s, W=1, B=1, C=4)
    cast(s, "Revival // Revenge", face=1, targets=["p2"])
    assert life(s, "p1") == 60 and life(s, "p2") == 20  # (40: half is 20)
    check(s)


# ---- Haven of the Spirit Dragon [1141] -------------------------------------------------------------------------------------------------------------------
def haven_table(cards):
    s = build(cards, ["Haven of the Spirit Dragon", "Shivan Dragon", "Grizzly Bears", "Ugin, the Spirit Dragon", "Jace, the Mind Sculptor"], [])
    haven = put(s, "Haven of the Spirit Dragon")
    for name in ("Shivan Dragon", "Grizzly Bears", "Ugin, the Spirit Dragon", "Jace, the Mind Sculptor"):
        act(s, "p1", type="move", card_ids=[card_named(s, name).id], to={"player": "p1", "zone": "graveyard"})
    mana(s, C=2)
    return s, haven


@pytest.mark.parametrize("name", ["Shivan Dragon", "Ugin, the Spirit Dragon"])
def test_haven_returns_a_dragon_creature_card_or_an_ugin_planeswalker_card_from_your_graveyard(cards, name):
    s, haven = haven_table(cards)
    activate(s, "p1", haven, "Return target", targets=[card_named(s, name).id])
    settle(s)
    assert zone_of(s, name) == "p1:hand" and zone_of(s, "Haven of the Spirit Dragon") == "p1:graveyard"  # (602.2b: sacrificed as a cost)
    check(s)


@pytest.mark.parametrize("name", ["Grizzly Bears", "Jace, the Mind Sculptor"])
def test_haven_cannot_target_another_kind_of_card(cards, name):
    s, haven = haven_table(cards)
    with pytest.raises(ActionError):
        activate(s, "p1", haven, "Return target", targets=[card_named(s, name).id])  # 115.1: neither a Dragon creature card nor an Ugin planeswalker card
    assert zone_of(s, "Haven of the Spirit Dragon") == "p1:battlefield"
    check(s)
