"""Wave 100E: damage sized by a value and X values (app/rules/xdamage100e.py; CR 2026-09-25). Real Oracle text
(tests/fixtures/wave100e_xdamage_cards.json, from data/cards.sqlite); every scenario checks the replay and a save and a load.

* 603.12 reflexive abilities whose amount is an object as it last existed (608.2h): the creature sacrificed (Minsc & Boo), the Army amassed
  (701.47c: Foray of Orcs), with an intervening "if" (603.4: Ajani, Nacatl Avenger), or after a counted draw (The Royal Scions).
* 701.47c "the Army you amassed" as a damage source and an amount (Widespread Brutality, Surrounded by Orcs).
* Damage sized by the source's counters, as it last existed when it was sacrificed (Dragonspark Reactor) or after it gained one (Pumpkin Bombs).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests import wave100e_kit as kit
from tests.game_helpers import act
from tests.test_rules_wave7b_activation import ability_index
from tests.wave9c_kit import build, check, life, mana, pt, put, to_hand
from tests.wave100e_kit import answer, chars, full_control, hand, loyal, pick, zone_of


@pytest.fixture()
def cards(settings):
    yield from kit.repo(settings)


@pytest.mark.parametrize("name", [c["name"] for c in kit.DATA])
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


# -- Minsc & Boo, Timeless Heroes: "−2: Sacrifice a creature. When you do, … X damage …, where X is that creature's power. If the sacrificed
# creature was a Hamster, draw X cards." ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("fodder", "dealt", "drawn"), [("Probe Hamster", 3, 3), ("Grizzly Bears", 2, 0)])
def test_minsc_and_boo_sacrifices_and_draws_only_for_a_hamster(cards, fodder, dealt, drawn):
    s = build(cards, ["Minsc & Boo, Timeless Heroes", fodder])
    minsc = loyal(s, "Minsc & Boo, Timeless Heroes")
    victim = put(s, fodder)
    before = hand(s)
    act(s, "p1", type="activate_ability", card_id=minsc.id, ability=ability_index(s, minsc, "Sacrifice a creature"))
    answer(s, victim.id, "p2")  # (the only creature: sacrificed; the reflexive ability's target, chosen as it is put on the stack: 603.12)
    assert zone_of(s, victim) == "p1:graveyard" and life(s, "p2") == 40 - dealt and hand(s) == before + drawn
    check(s)


def test_minsc_and_boo_reads_the_hamster_as_it_last_existed(cards):
    """608.2h: a Hamster with two +1/+1 counters is sacrificed: X is its last known power, 5 (it is a card in the graveyard by then)."""
    s = build(cards, ["Minsc & Boo, Timeless Heroes", "Probe Hamster"])
    minsc = loyal(s, "Minsc & Boo, Timeless Heroes")
    victim = put(s, "Probe Hamster")
    act(s, "p1", type="counter", card_ids=[victim.id], kind="+1/+1", delta=2)
    before = hand(s)
    act(s, "p1", type="activate_ability", card_id=minsc.id, ability=ability_index(s, minsc, "Sacrifice a creature"))
    answer(s, victim.id, "p2")
    assert life(s, "p2") == 35 and hand(s) == before + 5
    check(s)


# -- Ajani, Nacatl Avenger: "0: Create a 2/1 … Cat Warrior … When you do, if you control a red permanent other than Ajani, he deals damage equal
# to the number of creatures you control to any target." ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("red", [True, False])
def test_ajani_avenger_deals_damage_only_with_another_red_permanent(cards, red):
    """603.4: Ajani himself is red, so only another red permanent (Probe Ember) lets the reflexive ability trigger; it counts the creatures
    as it resolves (the new Cat Warrior and Grizzly Bears: 2)."""
    s = build(cards, ["Ajani, Nacatl Pariah // Ajani, Nacatl Avenger", "Probe Ember", "Grizzly Bears"])
    ajani = loyal(s, "Ajani, Nacatl Pariah // Ajani, Nacatl Avenger", face=1)
    put(s, "Grizzly Bears")
    if red:
        put(s, "Probe Ember")
    act(s, "p1", type="activate_ability", card_id=ajani.id, ability=ability_index(s, ajani, "Create a 2/1"))
    answer(s, "p2")
    cats = [c for c in s.state.cards.values() if c.name == "Cat Warrior" and c.zone == "p1:battlefield"]
    assert len(cats) == 1 and life(s, "p2") == (38 if red else 40)
    check(s)


def test_ajani_avenger_red_permanent_gone_before_it_resolves_does_nothing(cards):
    """603.4: the condition is checked again as the reflexive ability resolves: the Ember destroyed in response, no damage."""
    s = build(cards, ["Ajani, Nacatl Pariah // Ajani, Nacatl Avenger", "Probe Ember"])
    ajani = loyal(s, "Ajani, Nacatl Pariah // Ajani, Nacatl Avenger", face=1)
    ember = put(s, "Probe Ember")
    full_control(s)
    act(s, "p1", type="activate_ability", card_id=ajani.id, ability=ability_index(s, ajani, "Create a 2/1"))
    pick(s, "choose_one", "p2")
    assert len(s.state.zones["stack"]) == 1  # (the reflexive ability, about to resolve)
    act(s, "p1", type="move", card_ids=[ember.id], to={"player": "p1", "zone": "graveyard"})
    answer(s)
    assert life(s, "p2") == 40
    check(s)


# -- Foray of Orcs / Widespread Brutality / Surrounded by Orcs: "the amassed Army" (701.47c) --------------------------------------------------
def test_foray_of_orcs_deals_the_amassed_armys_power(cards):
    """701.47a: no Army, so a 0/0 Orc Army is made and gets two counters; the reflexive ability (its target chosen then, the 2023-06-16
    ruling) deals 2 to Grizzly Bears, a creature an opponent controls."""
    s = build(cards, ["Foray of Orcs"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    spell = to_hand(s, "Foray of Orcs")
    mana(s, R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    d = pick(s, "choose_one", bears.id)
    assert "p2" not in [o.id for o in d.options]  # (a creature an opponent controls: no player)
    answer(s)
    army = next(c for c in s.state.cards.values() if c.name == "Orc Army")
    assert army.counters.get("+1/+1") == 2 and zone_of(s, bears) == "p2:graveyard"
    check(s)


def test_foray_of_orcs_an_existing_army_is_the_one_amassed(cards):
    """701.47a: an Army you already control gets the counters (a 1/1 Zombie Army: 3/3, now also an Orc), and X is its power: 3."""
    s = build(cards, ["Foray of Orcs", "Probe Army"], ["Probe Wall"])
    army = put(s, "Probe Army")
    wall = put(s, "Probe Wall", "p2")
    spell = to_hand(s, "Foray of Orcs")
    mana(s, R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    pick(s, "choose_one", wall.id)
    answer(s)
    assert s.state.cards[wall.id].damage == 3 and pt(s, "Probe Army") == (3, 3) and "Orc" in chars(s, army).subtypes
    assert not any(c.name == "Orc Army" for c in s.state.cards.values())
    check(s)


def test_widespread_brutality_the_army_deals_its_power_to_each_non_army_creature(cards):
    """The Army is the source (120.3) and isn't dealt damage itself; every other creature (both players') is dealt 2."""
    s = build(cards, ["Widespread Brutality", "Grizzly Bears"], ["Probe Wall"])
    mine = put(s, "Grizzly Bears")
    wall = put(s, "Probe Wall", "p2")
    spell = to_hand(s, "Widespread Brutality")
    mana(s, B=1, R=2, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    answer(s)
    army = next(c for c in s.state.cards.values() if c.name == "Zombie Army")
    assert army.zone == "p1:battlefield" and army.damage == 0
    assert zone_of(s, mine) == "p1:graveyard" and s.state.cards[wall.id].damage == 2
    check(s)


def test_surrounded_by_orcs_mills_the_amassed_armys_power(cards):
    s = build(cards, ["Surrounded by Orcs", "Probe Army"])
    put(s, "Probe Army")
    before = len(s.state.zones["p2:library"])
    spell = to_hand(s, "Surrounded by Orcs")
    mana(s, U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"])
    answer(s)
    assert len(s.state.zones["p2:library"]) == before - 4  # (1/1 + three counters)
    check(s)


# -- Pumpkin Bombs / Dragonspark Reactor: damage sized by the source's own counters ------------------------------------------------------------
def test_pumpkin_bombs_deals_its_fuse_counters_and_changes_hands(cards):
    s = build(cards, ["Pumpkin Bombs", "Grizzly Bears", "Lightning Bolt"])
    bombs = put(s, "Pumpkin Bombs")
    act(s, "p1", type="counter", card_ids=[bombs.id], kind="fuse", delta=2)
    a, b = to_hand(s, "Grizzly Bears"), to_hand(s, "Lightning Bolt")
    before = hand(s)
    act(s, "p1", type="activate_ability", card_id=bombs.id, ability=0, targets=["p2"])
    answer(s, a.id, b.id)
    assert hand(s) == before - 2 + 3 and life(s, "p2") == 37
    assert s.state.cards[bombs.id].controller == "p2" and s.state.cards[bombs.id].counters.get("fuse") == 3
    check(s)


@pytest.mark.parametrize("creature", [True, False])
def test_dragonspark_reactor_deals_its_charge_counters_as_it_last_existed(cards, creature):
    """It was sacrificed to pay the cost: its three charge counters as it last existed size both parts; up to one target creature."""
    s = build(cards, ["Dragonspark Reactor"], ["Probe Wall"])
    reactor = put(s, "Dragonspark Reactor")
    act(s, "p1", type="counter", card_ids=[reactor.id], kind="charge", delta=3)
    wall = put(s, "Probe Wall", "p2")
    mana(s, C=4)
    act(s, "p1", type="activate_ability", card_id=reactor.id, ability=ability_index(s, reactor, "Sacrifice this artifact"),
        targets=["p2", *([wall.id] if creature else [])], target_counts=[1, 1 if creature else 0])
    answer(s)
    assert zone_of(s, reactor) == "p1:graveyard" and life(s, "p2") == 37 and s.state.cards[wall.id].damage == (3 if creature else 0)
    check(s)


# -- The Royal Scions: "−8: Draw four cards. When you do, … damage to any target equal to the number of cards in your hand." -----------------------
@pytest.mark.parametrize(("library", "dealt"), [(10, None), (3, 0)])
def test_royal_scions_triggers_only_when_four_cards_were_drawn(cards, library, dealt):
    """The 2019-10-04 rulings: the target is chosen after the draw, the damage is the hand as it resolves; drawing fewer than four (a library of
    three), it doesn't trigger."""
    s = build(cards, ["The Royal Scions"], forests=library)
    scions = loyal(s, "The Royal Scions")
    for cid in list(s.state.zones["p1:hand"]):
        act(s, "p1", type="move", card_ids=[cid], to={"player": "p1", "zone": "graveyard"})
    keep = list(s.state.zones["p1:library"])[:library]
    for cid in list(s.state.zones["p1:library"])[library:]:
        act(s, "p1", type="move", card_ids=[cid], to={"player": "p1", "zone": "exile"})
    assert len(s.state.zones["p1:library"]) == len(keep)
    act(s, "p1", type="activate_ability", card_id=scions.id, ability=ability_index(s, scions, "Draw four cards"))
    answer(s, "p2")
    assert hand(s) == min(4, library) and life(s, "p2") == 40 - (dealt if dealt is not None else 4)
    check(s)
