"""Affinity (CR 702.41): the spell costs {1} less for each permanent of that kind you control."""

from __future__ import annotations

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules.casting import castable
from tests.game_helpers import act, deck, enable
from tests.test_rules_effects import pass_until_stack_empty


def build(cards, *artifacts):
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Frogmite"), (1, "Sol Ring"), (1, "Sky-Skiff"), (7, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False), cards=cards)
    for name in artifacts:
        c = next(c for c in s.state.cards.values() if c.name == name)
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "battlefield"})
    s.state = enable(s.state)
    s = GameSession(s.state, cards=cards)
    act(s, "p1", type="pass_priority")
    frog = next(c for c in s.state.cards.values() if c.name == "Frogmite")
    act(s, "p1", type="move", card_ids=[frog.id], to={"zone": "hand"})
    return s, frog


def test_two_artifacts_make_it_cost_two(cards):
    s, frog = build(cards, "Sol Ring", "Sky-Skiff")
    assert castable(s.state, "p1", s.state.cards[frog.id], cards)  # {4} - 2 = {2}: Sol Ring pays it
    act(s, "p1", type="cast_spell", card_id=frog.id)
    pass_until_stack_empty(s)
    assert s.state.cards[frog.id].zone == "p1:battlefield"


def test_one_artifact_is_not_enough(cards):
    s, frog = build(cards, "Sol Ring")
    assert not castable(s.state, "p1", s.state.cards[frog.id], cards)  # {3}, but Sol Ring makes only {C}{C}
