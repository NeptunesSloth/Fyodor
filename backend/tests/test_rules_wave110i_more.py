"""Wave 110I (second session): real Oracle text; every scenario checks the replay and a save and a load.

* Curse of Conformity: base P/T 3/3 (613.4b) and no creature types (205.1a), nonlegendary only.
* Puppet Master: the payment is offered only once the creature card is back in hand; the Aura comes back from the graveyard (603.10a, 400.7).
* Rhuk, Hexgold Nabber: Equipment attached to the dying creature as it last was moves to Rhuk (701.3a, 603.10a); optional.
* The Moment: "phases out until The Moment leaves the battlefield" (610.3, 702.26a), untapped first, not tapped as it returns.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave110c_kit import answer, build, cast, check, make_db, mana, put, zone

EXTRA = [
    real("The Moment", "{1}{W}{U}", 3, "Legendary Artifact",
         "At the beginning of your upkeep, put a time counter on The Moment.\n{2}, {T}: Untap target creature you control. It phases out until The Moment leaves the battlefield.\n{3}, {T}: Destroy each nonland permanent with mana value less than or equal to the number of time counters on The Moment. Then sacrifice The Moment. Activate only as a sorcery.",
         None, "WU"),
    real("Curse of Conformity", "{3}{U}", 4, "Enchantment — Aura Curse",
         "Enchant player\nNonlegendary creatures enchanted player controls have base power and toughness 3/3 and lose all creature types.", None, "U"),
    real("Probe Legend", "{1}", 1, "Legendary Creature — Human Soldier", "", ("1", "1"), ""),
    real("Puppet Master", "{U}{U}{U}", 3, "Enchantment — Aura",
         "Enchant creature\nWhen enchanted creature dies, return that card to its owner's hand. If that card is returned to its owner's hand this way, you may pay {U}{U}{U}. If you do, return this card to its owner's hand.",
         None, "U"),
    real("Lightning Bolt", "{R}", 1, "Instant", "Lightning Bolt deals 3 damage to any target.", None, "R"),
    real("Rhuk, Hexgold Nabber", "{2}{R}", 3, "Legendary Creature — Goblin Rebel",
         "Trample, haste\nWhenever an equipped creature you control other than Rhuk attacks or dies, you may attach all Equipment attached to that creature to Rhuk.",
         ("2", "2"), "R"),
    real("Naturalize", "{1}{G}", 2, "Instant", "Destroy target artifact or enchantment.", None, "G"),
]
NAMES = ["The Moment", "Curse of Conformity", "Puppet Master", "Rhuk, Hexgold Nabber"]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_the_moment_phases_out_untapped_until_it_leaves(cards):
    s = build(cards, ["The Moment", "Naturalize", "Grizzly Bears"], [])
    moment, bear = put(s, "The Moment"), put(s, "Grizzly Bears")
    act(s, "p1", type="tap", card_ids=[bear.id])
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=moment.id, ability=1, targets=[bear.id])
    answer(s)
    assert zone(s, bear) == "p1:phased" and not s.state.cards[bear.id].tapped
    check(s)
    mana(s, G=1, C=1)
    cast(s, "Naturalize", [moment.id])
    answer(s)
    assert zone(s, bear) == "p1:battlefield" and not s.state.cards[bear.id].tapped
    check(s)


def test_curse_of_conformity_makes_nonlegendary_creatures_3_3_without_types(cards):
    s = build(cards, ["Curse of Conformity"], ["Grizzly Bears", "Probe Legend"])
    bear, legend = put(s, "Grizzly Bears", "p2"), put(s, "Probe Legend", "p2")
    mana(s, U=1, C=3)
    cast(s, "Curse of Conformity", ["p2"])
    answer(s)
    plan = Plan(s.state, "p1", s.cards, None)
    assert (plan.ch(s.state.cards[bear.id]).pt, "Bear" in plan.ch(s.state.cards[bear.id]).subtypes) == ((3, 3), False)
    assert (plan.ch(s.state.cards[legend.id]).pt, "Human" in plan.ch(s.state.cards[legend.id]).subtypes) == ((1, 1), True)
    check(s)


@pytest.mark.parametrize("pay", [True, False])
def test_puppet_master_returns_the_creature_and_itself_if_paid(cards, pay):
    s = build(cards, ["Puppet Master", "Lightning Bolt"], ["Grizzly Bears"])
    bear = put(s, "Grizzly Bears", "p2")
    mana(s, U=3)
    master = cast(s, "Puppet Master", [bear.id])
    answer(s)
    assert zone(s, master) == "p1:battlefield"
    mana(s, R=1, U=3 if pay else 0)
    cast(s, "Lightning Bolt", [bear.id])
    answer(s, "pay" if pay else "decline")
    assert zone(s, bear) == "p2:hand"
    assert zone(s, master) == ("p1:hand" if pay else "p1:graveyard")
    check(s)


@pytest.mark.parametrize("take", [True, False])
def test_rhuk_takes_the_equipment_of_a_dying_equipped_creature(cards, take):
    s = build(cards, ["Rhuk, Hexgold Nabber", "Grizzly Bears", "Bonesplitter", "Lightning Bolt"], [])
    rhuk, bear, gear = put(s, "Rhuk, Hexgold Nabber"), put(s, "Grizzly Bears"), put(s, "Bonesplitter")
    act(s, "p1", type="attach", card_ids=[gear.id], to=bear.id)
    mana(s, R=1)
    cast(s, "Lightning Bolt", [bear.id])
    answer(s, "yes" if take else "no")
    assert zone(s, bear) == "p1:graveyard"
    assert s.state.cards[gear.id].attached_to == (rhuk.id if take else None)
    check(s)
