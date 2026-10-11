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


EMPIRES = ("Crown of Empires", "Scepter of Empires", "Throne of Empires")


def empires(s, me, others, pid="p1"):
    for name in others:
        put(s, name, pid)
    c = put(s, me, pid)
    ready(s, c)
    return c


@pytest.mark.parametrize("others, lost", [(("Crown of Empires", "Throne of Empires"), 3), (("Crown of Empires",), 1), ((), 1)])
def test_scepter_of_empires_deals_three_with_the_other_two(cards, others, lost):
    s = build(cards, list(EMPIRES), [])
    scepter = empires(s, "Scepter of Empires", others)
    act(s, "p1", type="activate_ability", card_id=scepter.id, ability=0, targets=["p2"])
    settle(s)
    assert life(s, "p2") == 40 - lost
    s = reloaded(s)
    check(s)


@pytest.mark.parametrize("others, made", [(("Crown of Empires", "Scepter of Empires"), 5), (("Scepter of Empires",), 1)])
def test_throne_of_empires_makes_five_soldiers_with_the_other_two(cards, others, made):
    s = build(cards, list(EMPIRES), [])
    throne = empires(s, "Throne of Empires", others)
    mana(s, "p1", W=1)
    act(s, "p1", type="activate_ability", card_id=throne.id, ability=0)
    settle(s)
    assert sum(1 for c in s.state.cards.values() if c.name == "Soldier" and c.zone == "p1:battlefield") == made
    check(s)


@pytest.mark.parametrize("others, taken", [(("Scepter of Empires", "Throne of Empires"), True), (("Scepter of Empires",), False)])
def test_crown_of_empires_steals_the_creature_instead_of_tapping_it(cards, others, taken):
    s = build(cards, list(EMPIRES), ["Grizzly Bears"])
    crown = empires(s, "Crown of Empires", others)
    bears = put(s, "Grizzly Bears", "p2")
    mana(s, "p1", W=3)
    act(s, "p1", type="activate_ability", card_id=crown.id, ability=0, targets=[bears.id])
    settle(s)
    now = s.state.cards[bears.id]
    assert (now.controller == "p1", now.tapped) == (taken, not taken)
    s = reloaded(s)
    check(s)


def test_marauding_maulhorn_must_attack_unless_you_control_advocate_of_the_beast(cards):
    """"attacks each combat if able unless you control a creature named Advocate of the Beast": the named creature lifts the requirement."""
    from app.game.errors import ActionError

    s = build(cards, ["Marauding Maulhorn"], [])
    maul = put(s, "Marauding Maulhorn")
    ready(s, maul)
    act(s, "p1", type="pass_priority")  # → declare attackers
    with pytest.raises(ActionError, match="attacks each combat if able"):
        act(s, "p1", type="declare_attackers", attackers=[])
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": maul.id, "target": "p2"}])
    check(s)


def test_marauding_maulhorn_with_advocate_needs_not_attack(cards):
    s = build(cards, ["Marauding Maulhorn", "Advocate of the Beast"], [])
    maul = put(s, "Marauding Maulhorn")
    put(s, "Advocate of the Beast")
    ready(s, maul)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[])  # nothing is required
    check(s)
