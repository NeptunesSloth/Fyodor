"""Devoid (702.114), bushido (702.45), renown (702.112), bloodthirst (702.54)."""

from __future__ import annotations

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules import characteristics as chars
from app.rules.plan import Plan
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_combat import attack, automate, block, creature, table
from tests.test_rules_effects import mana, pass_until_stack_empty, run_until


def pt(s, cards, card):
    return Plan(s.state, "p1", cards, None).ch(s.state.cards[card.id]).pt


def test_devoid_is_colorless(cards):
    s = table(cards)
    act(s, "p1", type="create_token", player="p1", token={"name": "Drone", "type_line": "Token Creature — Eldrazi Drone",
                                                         "power": "1", "toughness": "1", "text": "Devoid", "colors": ["B"]})
    drone = next(c for c in s.state.cards.values() if c.name == "Drone")
    assert chars.of(drone, cards).colors == frozenset()


def test_bushido_pumps_blocker_and_blocked_attacker(cards):
    s = table(cards)
    samurai = creature(s, "p1", "Samurai", "2/2", "Bushido 1")
    guard = creature(s, "p2", "Guard", "2/2", "Bushido 2")
    automate(s)
    attack(s, (samurai, "p2"))
    block(s, "p2", (guard, samurai))
    for _ in range(8):
        if samurai.id not in s.state.cards or pt(s, cards, samurai) == (3, 3):
            break
        if s.state.rules.priority:
            act(s, s.state.rules.priority, type="pass_priority")
    # 3/3 Samurai vs 4/4 Guard: the Samurai dies, the Guard survives with 3 damage
    assert samurai.id not in s.state.cards or s.state.cards[samurai.id].zone == "p1:graveyard"
    assert s.state.cards[guard.id].zone == "p2:battlefield" and s.state.cards[guard.id].damage == 3


def test_renown_once(cards):
    s = table(cards)
    knight = creature(s, "p1", "Knight", "2/2", "Renown 1")
    automate(s)
    attack(s, (knight, "p2"))
    run_until(s, lambda s: s.state.players["p2"].life < 40 and not s.state.zones.get("stack"))
    pass_until_stack_empty(s)
    assert s.state.cards[knight.id].counters.get("+1/+1") == 1
    assert s.state.rules.object_id(knight.id) in s.state.rules.renowned


def test_bloodthirst(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(2, "Stormblood Berserker"), (8, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="draw", count=2)
    first, second = [c for c in zone(s.state, "p1", "hand") if s.state.cards[c].name == "Stormblood Berserker"]
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=first)
    pass_until_stack_empty(s)
    assert not s.state.cards[first].counters  # nobody was hurt yet
    s.state.rules.damaged["p2"] = s.state.turn.number  # (Bob was dealt damage this turn)
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=second)
    pass_until_stack_empty(s)
    assert s.state.cards[second].counters.get("+1/+1") == 2


def test_bounce_land_returns_a_land_you_choose(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Simic Growth Chamber"), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False), cards=cards)
    forest = next(c for c in s.state.cards.values() if c.name == "Forest")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "battlefield"})
    s = GameSession(enable(s.state), cards=cards)
    act(s, "p1", type="pass_priority")
    chamber = next(c for c in s.state.cards.values() if c.name == "Simic Growth Chamber")
    act(s, "p1", type="move", card_ids=[chamber.id], to={"zone": "hand"})
    act(s, "p1", type="play_land", card_id=chamber.id)
    for _ in range(6):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d.kind == "choose_cards" and {o.id for o in d.options} == {forest.id, chamber.id}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[forest.id])
    assert s.state.cards[forest.id].zone == "p1:hand" and s.state.cards[chamber.id].tapped
