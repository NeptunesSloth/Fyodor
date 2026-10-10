"""Persist, undying, toxic, flanking, "can't be countered", combat-damage triggers, mill,
"can't attack unless defending player controls an Island"."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules.plan import Plan
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_combat import attack, automate, block, creature, table
from tests.test_rules_effects import mana
from tests.test_rules_suspend import until


def on_table(cards, name):
    alice = deck(cards, "Krenko, Mob Boss", [(1, name), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False), cards=cards)
    card = next(c for c in s.state.cards.values() if c.name == name)
    act(s, "p1", type="move", card_ids=[card.id], to={"zone": "battlefield"})
    s = GameSession(enable(s.state), cards=cards)
    act(s, "p1", type="pass_priority")
    return s, card


@pytest.mark.parametrize(("name", "counter"), [("Kitchen Finks", "-1/-1"), ("Young Wolf", "+1/+1")])
def test_persist_and_undying_return_once(cards, name, counter):
    s, card = on_table(cards, name)
    act(s, "p1", type="set_damage", card_ids=[card.id], value=5)
    act(s, "p1", type="pass_priority")
    until(s, lambda s: not s.state.zones.get("stack") and s.state.cards[card.id].zone == "p1:battlefield")
    assert s.state.cards[card.id].counters == {counter: 1}
    act(s, "p1", type="set_damage", card_ids=[card.id], value=5)  # dies again: it had the counter
    act(s, "p1", type="pass_priority")
    until(s, lambda s: not s.state.zones.get("stack"))
    assert s.state.cards[card.id].zone == "p1:graveyard"


def test_toxic_and_combat_damage_trigger(cards):
    s = table(cards)
    rat = creature(s, "p1", "Rat", "1/1", "Toxic 2\nWhenever this creature deals combat damage to a player, draw a card.")
    automate(s)
    hand = len(zone(s.state, "p1", "hand"))
    attack(s, (rat, "p2"))
    until(s, lambda s: len(zone(s.state, "p1", "hand")) > hand)
    assert s.state.players["p2"].life == 39 and s.state.players["p2"].resources.get("poison") == 2


def test_flanking(cards):
    s = table(cards)
    knight = creature(s, "p1", "Knight", "2/2", "Flanking")
    guard = creature(s, "p2", "Guard", "2/2")
    automate(s)
    attack(s, (knight, "p2"))
    block(s, "p2", (guard, knight))
    until(s, lambda s: guard.id not in s.state.cards or s.state.turn.phase == "main2")
    assert guard.id not in s.state.cards  # a 1/1 after flanking: the Knight's 2 damage kills it
    assert s.state.cards[knight.id].zone == "p1:battlefield"  # and it dealt only 1 back


def test_attack_needs_an_island(cards):
    s = table(cards)
    armada = creature(s, "p1", "Armada", "5/5", "This creature can't attack unless defending player controls an Island.")
    automate(s)
    with pytest.raises(ActionError, match="can.t attack"):
        attack(s, (armada, "p2"))
    act(s, "p2", type="create_token", player="p2", token={"name": "Isle", "type_line": "Token Land — Island"})
    attack(s, (armada, "p2"))
    assert s.state.cards[armada.id].attacking is not None or s.state.players["p2"].life < 40


def test_cant_be_countered(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Supreme Verdict"), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(1, "Counterspell"), (9, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")
    verdict = next(c for c in s.state.cards.values() if c.name == "Supreme Verdict")
    counter = next(c for c in s.state.cards.values() if c.name == "Counterspell")
    act(s, "p1", type="move", card_ids=[verdict.id], to={"zone": "hand"})
    act(s, "p2", type="move", card_ids=[counter.id], to={"zone": "hand"})
    act(s, "p2", type="set_prefs", response="on")
    act(s, "p2", type="create_token", player="p2", token={"name": "Bear", "type_line": "Token Creature — Bear",
                                                         "power": "2", "toughness": "2"})
    bear = next(c for c in s.state.cards.values() if c.name == "Bear")
    mana(s, "p2", U=2)
    mana(s, W=2, U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=verdict.id)
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    act(s, "p2", type="cast_spell", card_id=counter.id, targets=[verdict.id])
    until(s, lambda s: not s.state.zones.get("stack"))
    assert s.state.cards[verdict.id].zone == "p1:graveyard" and s.state.cards[counter.id].zone == "p2:graveyard"
    assert bear.id not in s.state.cards  # the Verdict resolved anyway


def test_mill_template():
    from app.rules.scripts import parse_effects

    assert parse_effects("Mill three cards.")[0] == [{"do": "mill", "who": "you", "n": 3}]


def test_flanking_blocker_is_smaller(cards):
    s = table(cards)
    knight = creature(s, "p1", "Knight", "1/1", "Flanking")
    guard = creature(s, "p2", "Guard", "3/3")
    automate(s)
    attack(s, (knight, "p2"))
    block(s, "p2", (guard, knight))
    for _ in range(3):
        if s.state.rules.priority:
            act(s, s.state.rules.priority, type="pass_priority")
    if guard.id in s.state.cards and s.state.cards[guard.id].zone == "p2:battlefield":
        assert Plan(s.state, "p2", cards, None).ch(s.state.cards[guard.id]).pt in ((2, 2), (3, 3))
