"""Wave 110F: promotions on real Oracle text. Every scenario checks the replay and a save and a load (tests/wave9c_kit.check).

* 601.2c, 205.3m, 701.14a: "Choose two target creatures that share no creature types. Those creatures fight each other." (Rivals' Duel).
* 608.2b, 105.2: "Destroy two target nonblack creatures unless either one is a color the other isn't. They can't be regenerated." (Dead Ringers).
* 602.5, 605.1a: "Creatures with flying can't attack or block, and their activated abilities with {T} in their costs can't be activated." (Katabatic Winds).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave100n_multi import EXTRA as _BASE
from tests.test_rules_wave100n_multi import (
    answer,
    card_db,  # noqa: F401  (fixture DB with EXTRA)
    cast,
)
from tests.wave9c_kit import build, check, mana, put, to_hand, zone_of

EXTRA = [
    real('Katabatic Winds', '{2}{G}', 3, 'Enchantment',
         "Creatures with flying can't attack or block, and their activated abilities with {T} in their costs can't be activated.", None, 'G'),
    real("Rivals' Duel", '{3}{R}', 4, 'Sorcery',
         "Choose two target creatures that share no creature types. Those creatures fight each other.", None, 'R'),
    real('Test Giant 110F', '{3}{R}', 4, 'Creature — Giant', 'Vigilance', ('3', '3'), 'R'),
    real('Dead Ringers', '{3}{B}{B}', 5, 'Sorcery',
         "Destroy two target nonblack creatures unless either one is a color the other isn't. They can't be regenerated.", None, 'B'),
    real('Test Flyer', '{2}{U}', 3, 'Creature — Bird', 'Flying\n{T}: Draw a card.', ('1', '1'), 'U'),
]
_BASE.extend(EXTRA)  # the shared fixture DB builder reads this list
NAMES = ["Katabatic Winds", "Rivals' Duel", "Dead Ringers"]


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("creature,blocked", [("Test Flyer", True), ("Llanowar Elves", False)])
def test_katabatic_winds_stops_flyers_tap_abilities(cards, creature, blocked):
    s = build(cards, ["Katabatic Winds", creature])
    it = put(s, creature)
    c = to_hand(s, "Katabatic Winds")
    mana(s, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[])
    act(s, "p1", type="pass_priority")
    from tests.test_rules_wave100f_control import ch
    ab = next(x for x in ch(s, it).abilities if x.text.startswith("{T}"))
    if blocked:
        with pytest.raises(ActionError, match="can't be activated"):
            act(s, "p1", type="activate_ability", card_id=it.id, ability=ab.index)
    else:  # (Llanowar Elves is only summoning sick: the Winds don't touch it)
        with pytest.raises(ActionError, match="summoning sickness"):
            act(s, "p1", type="activate_ability", card_id=it.id, ability=ab.index)
    check(s)


def duel(cards, mine, theirs):
    s = build(cards, ["Rivals' Duel", mine], [theirs])
    a, b = put(s, mine), put(s, theirs, "p2")
    mana(s, R=1, C=3)
    return s, a, b


def test_rivals_duel_fights_unrelated_creatures(cards):
    s, bear, giant = duel(cards, "Grizzly Bears", "Test Giant 110F")
    cast(s, "Rivals' Duel", [bear.id, giant.id], target_counts=[2])
    answer(s)
    assert zone_of(s, "Grizzly Bears") == "p1:graveyard" and zone_of(s, "Test Giant 110F", "p2") == "p2:battlefield"
    check(s)


def test_rivals_duel_refuses_creatures_sharing_a_type(cards):
    s, bear, bear2 = duel(cards, "Grizzly Bears", "Grizzly Bears")
    with pytest.raises(ActionError, match="share no creature type"):
        cast(s, "Rivals' Duel", [bear.id, bear2.id], target_counts=[2])


@pytest.mark.parametrize("second,dies", [("Test Giant 110F", False), ("Grizzly Bears", True)])
def test_dead_ringers_needs_the_same_colors(cards, second, dies):
    s = build(cards, ["Dead Ringers", "Grizzly Bears"], [second])
    a, b = put(s, "Grizzly Bears"), put(s, second, "p2")
    mana(s, B=2, C=3)
    cast(s, "Dead Ringers", [a.id, b.id], target_counts=[2])
    answer(s)
    assert (zone_of(s, "Grizzly Bears") == "p1:graveyard") is dies
    check(s)
