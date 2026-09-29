"""Landfall triggers, "Activate only once each turn", and "target attacking or blocking creature"."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules.plan import Plan
from tests.game_helpers import act, deck, zone
from tests.test_rules_combat import attack, automate, creature, table
from tests.test_rules_effects import mana, pass_until_stack_empty


def power_of(s, cards, card):
    p = Plan(s.state, "p1", cards, None)
    return p.ch(s.state.cards[card.id]).pt


def test_landfall_pump(cards):
    s = table(cards)
    hound = creature(s, "p1", "Hound", "2/2", "Landfall — Whenever a land you control enters, this creature gets +2/+2 until end of turn.")
    automate(s)  # (in Alice's combat) — go back to a main phase: no attackers
    act(s, "p1", type="declare_attackers", attackers=[])
    for _ in range(6):
        if s.state.turn.phase == "main2":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "hand"})
    act(s, "p1", type="play_land", card_id=forest.id)
    pass_until_stack_empty(s)
    assert power_of(s, cards, hound) == (4, 4)


def test_once_each_turn(cards):
    s = table(cards)
    brute = creature(s, "p1", "Brute", "2/2", "{1}: This creature gets +1/+1 until end of turn. Activate only once each turn.")
    automate(s)
    act(s, "p1", type="declare_attackers", attackers=[])
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=brute.id, ability=0)
    pass_until_stack_empty(s)
    assert power_of(s, cards, brute) == (3, 3)
    with pytest.raises(ActionError, match="once each turn"):
        act(s, "p1", type="activate_ability", card_id=brute.id, ability=0)


def test_target_attacking_creature(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(10, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(1, "Sandblast"), (3, "Command Tower"), (6, "Island")])
    s = GameSession(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False), cards=cards)
    raider = creature(s, "p1", "Raider", "3/3")
    idle = creature(s, "p1", "Idle", "3/3")
    act(s, "p2", type="draw", count=1)
    towers = [c.id for c in s.state.cards.values() if c.name == "Command Tower"]
    act(s, "p2", type="move", card_ids=towers, to={"zone": "battlefield"})
    automate(s)
    act(s, "p2", type="set_prefs", response="on")  # Bob wants to respond during combat
    for _ in range(6):  # (Bob holds an instant: he may get priority before combat)
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    attack(s, (raider, "p2"))
    blast = next(c for c in zone(s.state, "p2", "hand") if s.state.cards[c].name == "Sandblast")
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    with pytest.raises(ActionError, match="legal target"):
        act(s, "p2", type="cast_spell", card_id=blast, targets=[idle.id])
    act(s, "p2", type="cast_spell", card_id=blast, targets=[raider.id])
    pass_until_stack_empty(s)
    assert raider.id not in s.state.cards or s.state.cards[raider.id].zone == "p1:graveyard"
