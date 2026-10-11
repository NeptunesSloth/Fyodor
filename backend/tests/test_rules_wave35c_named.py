"""Wave 35C: "instead" riders that read the permanents you control by name (CR 201.2, 608.2c, 614.15, 605.3a), real Oracle text
(tests/fixtures/wave35c_cards.json). Every scenario checks the replay and a save and a load.

* "If you control creatures named Mine Worker and Power Plant Worker, you gain 3 life instead." (Mine Worker, Power Plant Worker, Tower Worker's mana, the
  Empires artifacts): a permanent with each name, judged as the ability resolves (605.3a: a mana ability as it is activated).
* "That creature gets -4/-4 instead if you control a creature named Bogbrew Witch." (Festering Newt): the ability's own instruction replaced by its own
  rider (614.15 / 608.2c), judged once as the ability resolves (Gatherer ruling): the Witch leaving afterwards changes nothing.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, reloaded
from tests.wave35c_kit import bolt, pool, repository

FULL = ["Festering Newt", "Mine Worker", "Power Plant Worker", "Tower Worker"]


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


@pytest.mark.parametrize("name", FULL)
def test_the_promoted_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def ready(s, *cs):
    for c in cs:
        s.state.rules.controlled_since[c.id].turn = 0


@pytest.mark.parametrize("others, gained", [(("Power Plant Worker", "Tower Worker"), 3), (("Power Plant Worker",), 1), ((), 1)])
def test_mine_worker_gains_three_only_with_both_other_workers(cards, others, gained):
    s = build(cards, ["Mine Worker", "Power Plant Worker", "Tower Worker"], [])
    mine = put(s, "Mine Worker")
    for name in others:
        put(s, name)
    ready(s, mine)
    act(s, "p1", type="activate_ability", card_id=mine.id, ability=0)
    settle(s)
    assert life(s) == 40 + gained
    s = reloaded(s)
    check(s)


def test_the_names_are_those_of_creatures_you_control_not_an_opponents(cards):
    s = build(cards, ["Mine Worker", "Power Plant Worker"], ["Tower Worker"])
    mine = put(s, "Mine Worker")
    put(s, "Power Plant Worker")
    put(s, "Tower Worker", "p2")
    ready(s, mine)
    act(s, "p1", type="activate_ability", card_id=mine.id, ability=0)
    settle(s)
    assert life(s) == 41
    check(s)


@pytest.mark.parametrize("others, made", [(("Mine Worker", "Power Plant Worker"), {"C": 3}), (("Mine Worker",), {"C": 1})])
def test_tower_worker_adds_three_with_the_other_two(cards, others, made):
    s = build(cards, ["Mine Worker", "Power Plant Worker", "Tower Worker"], [])
    tower = put(s, "Tower Worker")
    for name in others:
        put(s, name)
    ready(s, tower)
    act(s, "p1", type="activate_ability", card_id=tower.id, ability=1)
    settle(s)
    assert pool(s) == made
    check(s)


@pytest.mark.parametrize("others, counters, power", [(("Mine Worker", "Tower Worker"), 2, 6), ((), 0, 6), (("Mine Worker",), 0, 6)])
def test_power_plant_worker_puts_counters_instead_of_the_pump_with_the_other_two(cards, others, counters, power):
    """608.2c: the pump is replaced by two +1/+1 counters (a 4/4 either way: +2/+2 until end of turn or two counters), only with both other Workers."""
    s = build(cards, ["Mine Worker", "Power Plant Worker", "Tower Worker"], [])
    plant = put(s, "Power Plant Worker")
    for name in others:
        put(s, name)
    mana(s, "p1", G=3)
    act(s, "p1", type="activate_ability", card_id=plant.id, ability=0)
    settle(s)
    assert s.state.cards[plant.id].counters.get("+1/+1", 0) == counters and pt(s, "Power Plant Worker") == (power, power)
    s = reloaded(s)
    check(s)


@pytest.mark.parametrize("witch, shrunk", [("p1", 4), (None, 1), ("p2", 1)])
def test_festering_newt_shrinks_by_four_with_your_bogbrew_witch_and_by_one_without(cards, witch, shrunk):
    """614.15: the same ability, replaced by its own rider when you control a Witch as it resolves. Bob's creature loses 1 toughness or 4; a Witch of Bob's does
    not count (it is a possible target, so the total over Bob's creatures is what is checked)."""
    s = build(cards, ["Festering Newt", "Bogbrew Witch", "Lightning Bolt"], ["Grizzly Bears", "Bogbrew Witch"])
    newt = put(s, "Festering Newt")
    if witch:
        put(s, "Bogbrew Witch", witch)
    put(s, "Grizzly Bears", "p2")
    act(s, "p2", type="counter", card_ids=[card_named(s, "Grizzly Bears", "p2").id], kind="+1/+1", delta=8)  # (a 10/10: it takes either)

    def toughness():
        return sum(pt(s, c.name, "p2")[1] for c in s.state.cards.values() if c.owner == "p2" and c.zone == "p2:battlefield")

    before = toughness()
    bolt(s, newt.id)  # the Newt dies; its ability targets a creature of Bob's (the first offered)
    assert s.state.cards[newt.id].zone == "p1:graveyard" and before - toughness() == shrunk
    s = reloaded(s)
    check(s)
