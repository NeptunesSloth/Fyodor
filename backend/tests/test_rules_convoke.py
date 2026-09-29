"""Convoke (CR 702.51): tap creatures to pay {1} or one mana of their color."""

from __future__ import annotations

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules.casting import castable
from tests.game_helpers import act, deck, enable
from tests.test_rules_effects import pass_until_stack_empty


def build(cards, tokens):
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Stoke the Flames"), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False), cards=cards)
    for i, colors in enumerate(tokens):
        act(s, "p1", type="create_token", player="p1", token={"name": f"T{i}", "type_line": "Token Creature — Test",
                                                             "power": "1", "toughness": "1", "colors": colors})
    stoke = next(c for c in s.state.cards.values() if c.name == "Stoke the Flames")
    act(s, "p1", type="move", card_ids=[stoke.id], to={"zone": "hand"})
    s = GameSession(enable(s.state), cards=cards)
    act(s, "p1", type="pass_priority")
    return s, stoke


def test_convoke_pays_with_creatures(cards):
    s, stoke = build(cards, [["R"], ["R"], [], ["G"]])
    assert castable(s.state, "p1", s.state.cards[stoke.id], cards)
    act(s, "p1", type="cast_spell", card_id=stoke.id, targets=["p2"])
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 36
    assert all(c.tapped for c in s.state.cards.values() if c.name.startswith("T"))


def test_convoke_needs_the_colors(cards):
    s, stoke = build(cards, [["R"], ["G"], [], ["G"]])  # only one red creature for {R}{R}
    assert not castable(s.state, "p1", s.state.cards[stoke.id], cards)


def test_not_enough_creatures(cards):
    s, stoke = build(cards, [["R"], ["R"], []])
    assert not castable(s.state, "p1", s.state.cards[stoke.id], cards)

