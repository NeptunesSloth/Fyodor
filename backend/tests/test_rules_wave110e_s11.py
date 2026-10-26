"""Wave 110E session 11: Oracle-text scenarios (each docstring names the rule)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import tests.test_rules_wave110e_cards as base
from app.rules import coverage
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110e_cards import answer, card_db, cast  # noqa: F401  (the fixture)
from tests.wave9c_kit import build, check, mana, pt, put, to_hand

THROWDOWN = real("Lethal Throwdown", "{1}{B}", 2, "Instant",
                 "As an additional cost to cast this spell, sacrifice a creature or sacrifice a modified creature. (Equipment, Auras you control, and counters are modifications.)\n"
                 "Destroy target creature or planeswalker. If the modified creature was sacrificed, draw a card.", None, "B")
BEAR = real("Test Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G")
BOON = real("Test Boon", "{1}{G}", 2, "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +2/+2.", None, "G")
GIANT = real("Test Giant", "{4}{G}", 5, "Creature — Giant", "", ("0", "9"), "G")
RAPTOR = real("Test Raptor", "{2}{R}", 3, "Creature — Dinosaur", "", ("3", "2"), "R")
_REAL = json.loads((Path(__file__).parent / "fixtures" / "wave110e_cards.json").read_text("utf-8"))  # real Oracle text, from data/cards.sqlite
FEUD = real("Bitter Feud", "{4}{R}", 5, "Enchantment", "As this enchantment enters, choose two players.\nIf a source controlled by one of the chosen players would deal "
            "damage to the other chosen player or a permanent that player controls, that source deals double that damage to that player or permanent instead.", None, "R")
BOLT = real("Test Bolt", "{R}", 1, "Instant", "Test Bolt deals 3 damage to any target.", None, "R")
base.EXTRA.extend([THROWDOWN, BEAR, BOON, RAPTOR, GIANT, FEUD, BOLT, *(card(c["name"], set_code="w110e", number=f"E{i:03d}", **{k: v for k, v in c.items() if k != "name"})
                                                    for i, c in enumerate(_REAL))])


@pytest.mark.parametrize("name", ["Lethal Throwdown", "Bitter Feud", "Saheeli's Lattice // Mastercraft Raptor"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize(("mod", "draws"), [(None, 0), ("counter", 1), ("aura", 1)])
def test_lethal_throwdown_draws_only_for_a_modified_sacrifice(cards, mod, draws):
    """700.9, 608.2h: the sacrificed creature is read as it last existed: a counter or an Aura on it makes it modified."""
    s = build(cards, ["Lethal Throwdown", "Test Bear", "Test Boon"], ["Test Bear"])
    mine = put(s, "Test Bear")
    victim = put(s, "Test Bear", "p2")
    if mod == "counter":
        s.state.cards[mine.id].counters["+1/+1"] = 1
    if mod == "aura":
        s.state.cards[put(s, "Test Boon").id].attached_to = mine.id
    hand = len(s.state.zones["p1:hand"])
    mana(s, B=1, C=1)
    cast(s, "Lethal Throwdown", [victim.id])
    answer(s, mine.id)
    assert s.state.cards[mine.id].zone == "p1:graveyard" and s.state.cards[victim.id].zone == "p2:graveyard"
    assert len(s.state.zones["p1:hand"]) == hand + draws
    check(s)


def test_mastercraft_raptor_power_is_the_total_power_of_the_crafted_cards(cards):
    """702.167a: the exiled Dinosaurs (power 3 + 3) are the craft materials; the back face's power is their total (toughness stays 4)."""
    s = build(cards, ["Saheeli's Lattice // Mastercraft Raptor", "Test Raptor", "Test Raptor"])
    lattice = put(s, "Saheeli's Lattice // Mastercraft Raptor")
    raptors = [c for c in s.state.cards.values() if c.name == "Test Raptor" and c.owner == "p1"]
    act(s, "p1", type="move", card_ids=[c.id for c in raptors], to={"player": "p1", "zone": "graveyard"})
    mana(s, R=1, C=4)
    act(s, "p1", type="activate_ability", card_id=lattice.id, ability=1, cost_choices=[{"component": 2, "cards": [c.id for c in raptors]}])
    answer(s)
    assert s.state.cards[lattice.id].face == 1 and all(s.state.cards[c.id].zone == "p1:exile" for c in raptors)
    assert pt(s, "Saheeli's Lattice // Mastercraft Raptor") == (6, 4)
    check(s)


def _three(cards, mine, carols=("Test Bolt",)):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in mine), (10, "Mountain")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(1, "Test Giant"), (1, "Test Bolt"), (10, "Mountain")])
    carol = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in carols), (10, "Mountain")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob), PlayerSetup("Carol", cards=carol)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def _feud(cards):
    s = _three(cards, ["Bitter Feud", "Test Bolt", "Test Bear", "Test Giant"])
    mana(s, R=1, C=4)
    cast(s, "Bitter Feud")
    answer(s, "p1,p2")
    feud = next(c for c in s.state.cards.values() if c.name == "Bitter Feud")
    assert feud.zone == "p1:battlefield" and feud.choices.get("Chosen players") == "Alice and Bob"
    return s


@pytest.mark.parametrize(("hit", "doubled"), [("p2", True), ("p3", False), ("p1", False), ("bear", True), ("mybear", False)])
def test_bitter_feud_doubles_damage_between_the_two_chosen_players(cards, hit, doubled):
    """614.12a: p1 chooses two players (p1, p2) as it enters; 614.1: a source controlled by one chosen player deals double to the OTHER one or its permanents only."""
    s = _feud(cards)
    mybear = put(s, "Test Giant")
    big = put(s, "Test Giant", "p2") if hit == "bear" else mybear
    target = {"bear": big.id, "mybear": mybear.id}.get(hit, hit)
    before = {p: s.state.players[p].life for p in ("p1", "p2", "p3")}
    mana(s, R=1)
    cast(s, "Test Bolt", [target])
    answer(s)
    if hit.startswith("p"):
        assert before[hit] - s.state.players[hit].life == (6 if doubled else 3)
    else:
        assert s.state.cards[big.id].damage == (6 if doubled else 3)
    check(s)


def test_bitter_feud_the_other_chosen_player_and_an_unchosen_source(cards):
    """614.1: Bob's source hitting Alice is doubled (each chosen player's sources count); Carol's source (not chosen) hitting Alice is not."""
    s = _feud(cards)
    for pid, doubled in (("p2", True), ("p3", False)):
        before = s.state.players["p1"].life
        bolt = to_hand(s, "Test Bolt", pid)
        s.state.rules.priority = pid
        mana(s, pid, R=1)
        act(s, pid, type="cast_spell", card_id=bolt.id, targets=["p1"])
        answer(s)
        assert before - s.state.players["p1"].life == (6 if doubled else 3)
    check(s)
