"""Wave 52D: counter wordings one clause short of FULL (CR 2026-09-25), real Oracle text (tests/fixtures/wave52d_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 708.11 / 122.6: Hooded Hydra, Bubble Smuggler - "As this creature is turned face up, put five +1/+1 counters on it." is applied while it is turned up: a 0/0 lives.
* 614.1c / 122.6: Ascendant Acolyte (a counter for each +1/+1 counter among your other creatures), Embodiment of Agonies (for each different mana cost among the
  nonland cards in your graveyard: a card with no mana cost has no cost to count, 202.1b).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import settle
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of
from tests.wave52d_kit import open_repo

NAMES = ["Hooded Hydra", "Bubble Smuggler", "Ascendant Acolyte", "Embodiment of Agonies", "Valkyrie's Call", "Pugnacious Hammerskull", "Essence Symbiote", "Sigil Captain"]


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", NAMES)
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def counters(s, name, pid="p1", kind="+1/+1"):
    return s.state.cards[card_named(s, name, pid).id].counters.get(kind, 0)


def power_toughness(s, name):
    c = s.state.cards[card_named(s, name).id]
    return Plan(s.state, "p1", s.cards, None).ch(c).pt


# ---- Hooded Hydra, Bubble Smuggler --------------------------------------------------------------------------------------------------------------
def face_down(s, name, cost):
    mana(s, "p1", C=3)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, name).id, face_down=True)
    settle(s)
    assert s.state.cards[card_named(s, name).id].face_down
    mana(s, "p1", **cost)


def test_hooded_hydra_gets_its_counters_as_it_is_turned_up_and_survives(cards):
    s = build(cards, ["Hooded Hydra"])
    face_down(s, "Hooded Hydra", {"G": 2, "C": 3})
    act(s, "p1", type="turn_face_up", card_id=card_named(s, "Hooded Hydra").id)
    assert zone_of(s, "Hooded Hydra") == "p1:battlefield" and counters(s, "Hooded Hydra") == 5
    assert power_toughness(s, "Hooded Hydra") == (5, 5)  # a 0/0 with the counters already on it: no state-based action took it
    check(s)


def test_bubble_smuggler_gets_four_counters(cards):
    s = build(cards, ["Bubble Smuggler"])
    face_down(s, "Bubble Smuggler", {"U": 2, "C": 4})
    act(s, "p1", type="turn_face_up", card_id=card_named(s, "Bubble Smuggler").id)
    assert counters(s, "Bubble Smuggler") == 4
    check(s)


def test_hooded_hydra_cast_face_up_has_no_counters_from_it(cards):
    s = build(cards, ["Hooded Hydra"])
    mana(s, "p1", G=2, C=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Hooded Hydra").id, x_value=2)
    settle(s)
    assert counters(s, "Hooded Hydra") == 2  # only the X it was cast with: "turned face up" never happened
    check(s)


# ---- Ascendant Acolyte --------------------------------------------------------------------------------------------------------------------------
def test_acolyte_enters_with_a_counter_for_each_counter_among_your_other_creatures(cards):
    s = build(cards, ["Ascendant Acolyte", "Llanowar Elves", "Perilous Myr"])
    elves, myr = put(s, "Llanowar Elves"), put(s, "Perilous Myr")
    act(s, "p1", type="counter", card_ids=[elves.id], kind="+1/+1", delta=2)
    act(s, "p1", type="counter", card_ids=[myr.id], kind="+1/+1", delta=1)
    act(s, "p1", type="counter", card_ids=[myr.id], kind="flying", delta=3)  # another kind: not counted
    mana(s, "p1", G=1, C=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Ascendant Acolyte").id)
    settle(s)
    assert counters(s, "Ascendant Acolyte") == 3
    check(s)


def test_acolyte_does_not_count_its_own_counters(cards):
    s = build(cards, ["Ascendant Acolyte"])
    mana(s, "p1", G=1, C=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Ascendant Acolyte").id)
    settle(s)
    assert counters(s, "Ascendant Acolyte") == 0
    check(s)


# ---- Embodiment of Agonies ----------------------------------------------------------------------------------------------------------------------
def test_embodiment_counts_different_mana_costs_among_nonland_cards_in_the_graveyard(cards):
    s = build(cards, ["Embodiment of Agonies", "Lightning Bolt", "Lightning Bolt", "Counterspell", "Forest"])
    for c in [c for c in s.state.cards.values() if c.owner == "p1" and c.name in ("Lightning Bolt", "Counterspell", "Forest")][:5]:
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})
    yard = sorted(s.state.cards[c].name for c in s.state.zones["p1:graveyard"])
    assert yard.count("Lightning Bolt") == 2 and "Counterspell" in yard  # two Bolts share {R}: one cost; Counterspell {U}{U}; the lands are not counted
    mana(s, "p1", B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Embodiment of Agonies").id)
    settle(s)
    assert counters(s, "Embodiment of Agonies") == 2
    check(s)


# ---- Valkyrie's Call ----------------------------------------------------------------------------------------------------------------------------
def test_valkyries_call_returns_a_dead_creature_with_a_counter_flying_and_as_an_angel(cards):
    s = build(cards, ["Valkyrie's Call", "Llanowar Elves", "Lightning Bolt"])
    put(s, "Valkyrie's Call")
    elves = put(s, "Llanowar Elves")
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[elves.id])
    settle(s)
    back = card_named(s, "Llanowar Elves")
    assert back.zone == "p1:battlefield" and back.counters.get("+1/+1") == 1
    ch = Plan(s.state, "p1", s.cards, None).ch(back)
    assert "flying" in ch.keywords and "Angel" in ch.subtypes and "Elf" in ch.subtypes and ch.pt == (2, 2)  # 1/1 with a counter; Angel in addition
    check(s)


def test_valkyries_call_ignores_an_angel(cards):
    s = build(cards, ["Valkyrie's Call", "Llanowar Elves", "Lightning Bolt"])
    put(s, "Valkyrie's Call")
    elves = put(s, "Llanowar Elves")
    mana(s, "p1", R=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[elves.id])
    settle(s)
    assert zone_of(s, "Llanowar Elves") == "p1:battlefield"  # came back as an Angel...
    act(s, "p1", type="move", card_ids=[to_hand(s, "Lightning Bolt").id], to={"zone": "hand"})
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=[card_named(s, "Llanowar Elves").id])
    settle(s)
    assert zone_of(s, "Llanowar Elves") == "p1:graveyard"  # ...so it does not return a second time
    check(s)


# ---- Pugnacious Hammerskull ---------------------------------------------------------------------------------------------------------------------
def attack_with(s, name):
    from tests.test_rules_wave34b_activated import attack, next_turn

    next_turn(s)
    attack(s, card_named(s, name))
    settle(s)


def test_hammerskull_attacking_alone_among_dinosaurs_gets_a_stun_counter(cards):
    s = build(cards, ["Pugnacious Hammerskull"])
    put(s, "Pugnacious Hammerskull")
    attack_with(s, "Pugnacious Hammerskull")
    assert counters(s, "Pugnacious Hammerskull", kind="stun") == 1
    check(s)


def test_hammerskull_with_another_dinosaur_gets_no_counter(cards):
    s = build(cards, ["Pugnacious Hammerskull", "Ripjaw Raptor"])
    put(s, "Pugnacious Hammerskull")
    put(s, "Ripjaw Raptor")
    attack_with(s, "Pugnacious Hammerskull")
    assert counters(s, "Pugnacious Hammerskull", kind="stun") == 0
    check(s)


# ---- Essence Symbiote ---------------------------------------------------------------------------------------------------------------------------
def test_essence_symbiote_adds_a_counter_and_two_life_when_a_creature_you_control_mutates(cards):
    from tests.test_rules_wave18d_merged import mutate

    s = build(cards, ["Essence Symbiote", "Gemrazer", "Llanowar Elves"])
    put(s, "Essence Symbiote")
    elves = put(s, "Llanowar Elves")
    before = s.state.players["p1"].life
    mutate(s, "Gemrazer", elves, G=3)
    host = s.state.cards[elves.id]
    assert host.name == "Gemrazer" and host.counters.get("+1/+1") == 1 and s.state.players["p1"].life == before + 2
    check(s)


# ---- Sigil Captain ------------------------------------------------------------------------------------------------------------------------------
def test_sigil_captain_puts_two_counters_on_a_1_1_that_enters_and_ignores_a_2_2(cards):
    s = build(cards, ["Sigil Captain", "Llanowar Elves", "Grizzly Bears"])
    put(s, "Sigil Captain")
    mana(s, "p1", G=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Llanowar Elves").id)
    settle(s)
    mana(s, "p1", G=2)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Grizzly Bears").id)
    settle(s)
    assert counters(s, "Llanowar Elves") == 2 and power_toughness(s, "Llanowar Elves") == (3, 3)
    assert counters(s, "Grizzly Bears") == 0
    check(s)
