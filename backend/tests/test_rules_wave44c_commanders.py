"""Wave 44C (more commanders one line short of FULL, CR 2026-09-25), real Oracle text (tests/fixtures/wave44c_cards.json). Every scenario checks the replay and a save and a load.

* 508.1, 306.5: "Planeswalkers you control have "No more than one creature can attack this planeswalker each combat."" (Tomik, Orzhov Lawmage [17789]) - for each planeswalker,
  not for its controller or the table.
* 510.1a: "Sacrifice a Food: Until end of turn, target creature you control assigns combat damage equal to its toughness rather than its power." (Bill the Pony [8848]).
* 603.2, 205.3m: Folk Hero [3783]: "Commander creatures you own have "Whenever you cast a spell that shares a creature type with this creature, draw a card. This ability triggers only
  once each turn."" - Haunted One [4736]: "… "Whenever this creature becomes tapped, it and other creatures you control that share a creature type with it each get +2/+0 and gain
  undying until end of turn."" (the commander is Krenko, Mob Boss, a Goblin Warrior).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, attack, next_turn, settle, to_phase
from tests.wave44c_kit import DATA, ch, life, open_cards
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


@pytest.mark.parametrize("name", ["Tomik, Orzhov Lawmage", "Bill the Pony", "Folk Hero", "Haunted One"])
def test_coverage_full(cards, name):
    data = next(c for c in DATA if c["name"] == name)
    assert coverage.of_card_data({**data, "faces": data.get("card_faces") or [data], "oracle_id": name}).level == "FULL"


def base(name):
    data = next(c for c in DATA if c["name"] == name)
    return int(data["power"]), int(data["toughness"])


# ---- Tomik, Orzhov Lawmage [17789] --------------------------------------------------------------------------------------------------------------------
def tomik_table(cards):
    s = build(cards, ["Tomik, Orzhov Lawmage", "Gideon Jura"], ["Hill Giant", "Grizzly Bears"])
    put(s, "Tomik, Orzhov Lawmage")
    gideon = put(s, "Gideon Jura")
    act(s, "p1", type="counter", card_ids=[gideon.id], kind="loyalty", delta=6)
    giant, bears = put(s, "Hill Giant", "p2"), put(s, "Grizzly Bears", "p2")
    settle(s)
    to_phase(s, "declare_attackers", turn=2)  # Bob's turn
    return s, gideon, giant, bears


def test_tomik_lets_only_one_creature_attack_each_planeswalker(cards):
    s, gideon, giant, bears = tomik_table(cards)
    with pytest.raises(ActionError, match="No more than 1 creature can attack Gideon Jura each combat"):
        act(s, "p2", type="declare_attackers", attackers=[{"card_id": giant.id, "target": gideon.id}, {"card_id": bears.id, "target": gideon.id}])
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": giant.id, "target": gideon.id}, {"card_id": bears.id, "target": "p1"}])  # one at each
    check(s)


def test_tomik_does_not_limit_the_attacks_on_its_controller(cards):
    s, gideon, giant, bears = tomik_table(cards)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": giant.id, "target": "p1"}, {"card_id": bears.id, "target": "p1"}])
    check(s)


# ---- Bill the Pony [8848] ----------------------------------------------------------------------------------------------------------------------------
def test_bill_makes_a_creature_assign_its_toughness_this_turn(cards):
    s = build(cards, ["Bill the Pony"], [])
    bill = put(s, "Bill the Pony")  # 1/4
    for _ in range(2):
        act(s, "p1", type="create_token", player="p1", token={"name": "Food", "type_line": "Token Artifact — Food", "power": "", "toughness": "", "colors": []})
    settle(s)
    next_turn(s)
    activate(s, "p1", bill, "Sacrifice a Food", targets=[bill.id])
    settle(s)
    assert sum(1 for c in s.state.cards.values() if c.name == "Food" and c.zone == "p1:battlefield") == 1
    attack(s, bill)
    to_phase(s, "main2")
    assert life(s, "p2") == 40 - base("Bill the Pony")[1]  # 4, not 1
    next_turn(s)
    attack(s, bill)
    to_phase(s, "main2")
    assert life(s, "p2") == 40 - 4 - base("Bill the Pony")[0]  # only this turn: its power again
    check(s)


# ---- Folk Hero [3783] --------------------------------------------------------------------------------------------------------------------------------
def hand(s):
    return len(s.state.zones["p1:hand"])


def test_folk_hero_draws_when_the_commander_shares_a_creature_type_with_the_spell(cards):
    s = build(cards, ["Folk Hero", "Goblin Piker", "Hill Giant"], [])
    put(s, "Folk Hero")
    act(s, "p1", type="move", card_ids=[card_named(s, "Krenko, Mob Boss").id], to={"player": "p1", "zone": "battlefield"})  # the commander, a Goblin Warrior
    settle(s)
    piker, giant = to_hand(s, "Goblin Piker"), to_hand(s, "Hill Giant")
    n = hand(s)
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=piker.id)
    settle(s)
    assert hand(s) == n - 1 + 1  # a Goblin: the commander draws
    mana(s, R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=giant.id)
    settle(s)
    assert hand(s) == n - 1 + 1 - 1  # a Giant shares no type with a Goblin Warrior
    check(s)


# ---- Haunted One [4736] ------------------------------------------------------------------------------------------------------------------------------
def test_haunted_one_pumps_the_tapped_commander_and_the_creatures_that_share_its_type(cards):
    s = build(cards, ["Haunted One", "Goblin Piker", "Hill Giant"], [])
    put(s, "Haunted One")
    krenko = put(s, "Krenko, Mob Boss")  # the commander, a Goblin Warrior
    piker, giant = put(s, "Goblin Piker"), put(s, "Hill Giant")
    settle(s)
    next_turn(s)
    (kp, kt), (gp, gt), (hp, ht) = pt(s, "Krenko, Mob Boss"), pt(s, "Goblin Piker"), pt(s, "Hill Giant")
    attack(s, krenko)  # tapping it to attack
    settle(s)
    assert pt(s, "Krenko, Mob Boss") == (kp + 2, kt) and "undying" in ch(s, krenko).keywords
    assert pt(s, "Goblin Piker") == (gp + 2, gt) and "undying" in ch(s, piker).keywords  # a Goblin too
    assert pt(s, "Hill Giant") == (hp, ht) and "undying" not in ch(s, giant).keywords  # a Giant is not
    check(s)
