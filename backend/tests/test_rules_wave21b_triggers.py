"""Wave 21B: the trigger long tail, fifth pass (CR 2026-09-25). Real Oracle text; every scenario checks the replay and a save and a load.

* 115.1 / 603.2: "becomes the target of a spell or ability, … that spell's / that spell or ability's controller" - the player whose
  spell or ability targeted it (any controller, not only an opponent's).
* 603.4: "if that player has one or fewer cards in hand, they lose 3 life" - "they" after an intervening "if".
* 608.2c: "for each opponent who has more cards in hand than you / one or fewer cards in hand" - counted as it resolves.
* 701.21a: "Sacrifice a creature. If you can't, sacrifice this artifact." - a mandatory one-object sacrifice that found no object.
* 601.2h / 202.3b: "whenever you cast a spell, you lose life equal to its mana value", "if the amount of mana spent to cast it was
  less than its mana value, … loses life equal to the difference".
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import run_until
from tests.test_rules_wave12a_counters_keywords import answer, real
from tests.wave9c_kit import build, card_named, check, life, put, to_hand

EXTRA = [
    real('Retromancer', '{2}{R}{R}', 4, 'Creature — Lizard Shaman', "Whenever this creature becomes the target of a spell or ability, this creature deals 3 damage to that spell or ability's controller.", ("3", "3"), 'R'),
    real('Forsaken Wastes', '{2}{B}', 3, 'World Enchantment', "Players can't gain life.\nAt the beginning of each player's upkeep, that player loses 1 life.\nWhenever this enchantment becomes the target of a spell, that spell's controller loses 5 life.", None, 'B'),
    real('Lava Runner', '{1}{R}{R}', 3, 'Creature — Lizard', "Haste\nWhenever this creature becomes the target of a spell or ability, that spell or ability's controller sacrifices a land of their choice.", ("2", "2"), 'R'),
    real('Shrieking Affliction', '{B}', 1, 'Enchantment', "At the beginning of each opponent's upkeep, if that player has one or fewer cards in hand, they lose 3 life.", None, 'B'),
    real('Eldrazi Monument', '{5}', 5, 'Artifact', "Creatures you control get +1/+1 and have flying and indestructible.\nAt the beginning of your upkeep, sacrifice a creature. If you can't, sacrifice this artifact.", None),
    real('Rust Elemental', '{4}', 4, 'Artifact Creature — Elemental', "Flying\nAt the beginning of your upkeep, sacrifice another artifact. If you can't, tap this creature and you lose 4 life.", ("4", "4")),
    real('Wojek Investigator', '{2}{W}', 3, 'Creature — Angel Detective', 'Flying, vigilance\nAt the beginning of your upkeep, investigate once for each opponent who has more cards in hand than you. (To investigate, create a Clue token. It\'s an artifact with "{2}, Sacrifice this token: Draw a card.")', ("2", "4"), 'W'),
    real('Teval, Arbiter of Virtue', '{2}{B}{G}{U}', 5, 'Legendary Creature — Spirit Dragon', 'Flying, lifelink\nSpells you cast have delve. (Each card you exile from your graveyard while casting those spells pays for {1}.)\nWhenever you cast a spell, you lose life equal to its mana value.', ("6", "6"), 'BGU'),
    real('Ancient Cellarspawn', '{1}{B}{B}', 3, 'Enchantment Creature — Horror', "Each spell you cast that's a Demon, Horror, or Nightmare costs {1} less to cast.\nWhenever you cast a spell, if the amount of mana spent to cast it was less than its mana value, target opponent loses life equal to the difference.", ("3", "3"), 'B'),
    real('Probe Burst', '{R}', 1, 'Instant', 'Probe Burst deals 1 damage to any target.', None, 'R'),
    real('Probe Smite', '{W}', 1, 'Instant', 'Destroy target enchantment.', None, 'W'),
    real('Probe Soldier', '{1}{W}', 2, 'Creature — Human Soldier', '', ("1", "1"), 'W'),
    real('Probe Rock', '{3}', 3, 'Artifact', '', None),
    real('Probe Horror', '{1}{B}{B}', 3, 'Creature — Horror', '', ("2", "2"), 'B'),
]

NAMES = [e["name"] for e in EXTRA if not e["name"].startswith("Probe")]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_coverage_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def hand_size(s, pid, n):
    hand = list(s.state.zones[f"{pid}:hand"])
    while len(hand) < n:
        act(s, pid, type="draw", count=1)
        hand = list(s.state.zones[f"{pid}:hand"])
    if len(hand) > n:
        act(s, pid, type="move", card_ids=hand[n:], to={"zone": "library", "player": pid})


def on_battlefield(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.name == name and c.zone == f"{pid}:battlefield"]


def test_the_player_whose_spell_targeted_it_is_dealt_3(cards):
    s = build(cards, ["Retromancer", "Probe Burst"], ["Probe Burst"])
    retro = put(s, "Retromancer")
    mine, burst = to_hand(s, "Probe Burst"), to_hand(s, "Probe Burst", "p2")
    act(s, "p1", type="add_mana", player="p1", mana={"R": 1})
    act(s, "p2", type="add_mana", player="p2", mana={"R": 1})
    act(s, "p1", type="cast_spell", card_id=mine.id, targets=["p2"])  # Alice's own spell on Bob; Bob responds
    act(s, "p2", type="cast_spell", card_id=burst.id, targets=[retro.id])
    answer(s)
    assert life(s, "p2") == 40 - 1 - 3 and life(s, "p1") == 40
    check(s)


def test_that_spells_controller_loses_5_life(cards):
    s = build(cards, ["Forsaken Wastes", "Probe Burst"], ["Probe Smite"])
    wastes = put(s, "Forsaken Wastes")
    mine, burst = to_hand(s, "Probe Burst"), to_hand(s, "Probe Smite", "p2")
    act(s, "p1", type="add_mana", player="p1", mana={"R": 1})
    act(s, "p2", type="add_mana", player="p2", mana={"W": 1})
    act(s, "p1", type="cast_spell", card_id=mine.id, targets=["p2"])
    act(s, "p2", type="cast_spell", card_id=burst.id, targets=[wastes.id])
    answer(s)
    assert life(s, "p2") == 40 - 1 - 5 and life(s, "p1") == 40
    check(s)


@pytest.mark.parametrize(("hand", "loss"), [(1, 3), (0, 3), (2, 0)])
def test_they_lose_3_if_that_player_has_one_or_fewer_cards(cards, hand, loss):
    s = build(cards, ["Shrieking Affliction"], [])
    put(s, "Shrieking Affliction")
    hand_size(s, "p2", hand)
    run_until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")
    assert life(s, "p2") == 40 - loss and life(s, "p1") == 40
    check(s)


@pytest.mark.parametrize(("bob_hand", "clues"), [(6, 1), (0, 0)])
def test_investigate_once_for_each_opponent_with_more_cards_in_hand(cards, bob_hand, clues):
    s = build(cards, ["Wojek Investigator"], [])
    put(s, "Wojek Investigator")
    hand_size(s, "p1", 2)
    hand_size(s, "p2", bob_hand)
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    assert len(on_battlefield(s, "Clue")) == clues
    check(s)


def test_sacrifice_a_creature_if_you_cant_sacrifice_the_artifact(cards):
    s = build(cards, ["Eldrazi Monument"], [])
    put(s, "Eldrazi Monument")
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    assert not on_battlefield(s, "Eldrazi Monument")  # no creature to sacrifice
    check(s)


def test_the_creature_is_sacrificed_and_the_artifact_stays(cards):
    s = build(cards, ["Eldrazi Monument", "Probe Soldier"], [])
    put(s, "Eldrazi Monument")
    put(s, "Probe Soldier")
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    assert on_battlefield(s, "Eldrazi Monument") and not on_battlefield(s, "Probe Soldier")
    check(s)


def test_if_you_cant_sacrifice_another_artifact_tap_it_and_lose_4(cards):
    s = build(cards, ["Rust Elemental"], [])
    put(s, "Rust Elemental")
    run_until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    assert s.state.cards[card_named(s, "Rust Elemental").id].tapped and life(s) == 36
    check(s)


def test_lose_life_equal_to_the_mana_value_of_each_spell_cast(cards):
    s = build(cards, ["Teval, Arbiter of Virtue", "Probe Rock"], [])
    put(s, "Teval, Arbiter of Virtue")
    rock = to_hand(s, "Probe Rock")
    act(s, "p1", type="add_mana", player="p1", mana={"C": 3})
    act(s, "p1", type="cast_spell", card_id=rock.id)
    answer(s)
    assert life(s) == 40 - 3
    check(s)


def test_less_mana_spent_than_the_mana_value_costs_the_difference(cards):
    s = build(cards, ["Ancient Cellarspawn", "Probe Horror"], [])
    put(s, "Ancient Cellarspawn")
    horror = to_hand(s, "Probe Horror")
    act(s, "p1", type="add_mana", player="p1", mana={"B": 2})  # costs {1} less: 2 mana spent for a mana value of 3
    act(s, "p1", type="cast_spell", card_id=horror.id)
    answer(s)
    assert life(s, "p2") == 40 - 1
    check(s)
