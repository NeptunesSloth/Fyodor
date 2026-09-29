"""Flashback (CR 702.34): cast from your graveyard for the flashback cost, then exile it."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules.view import hints
from tests.game_helpers import act, deck, enable
from tests.test_rules_effects import mana, pass_until_stack_empty, replay_matches


def build(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Firebolt"), (1, "Lightning Bolt"), (8, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's first main phase
    act(s, "p1", type="draw", count=2)
    return s


def card(s, name):
    return next(c for c in s.state.cards.values() if c.name == name)


def test_cast_from_hand_then_flashback_then_exile(cards):
    s = build(cards)
    fb = card(s, "Firebolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=fb.id, targets=["p2"])
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 38 and card(s, "Firebolt").zone == "p1:graveyard"
    mana(s, R=1)
    with pytest.raises(ActionError):  # the flashback cost is {4}{R}, not {R}
        act(s, "p1", type="cast_spell", card_id=fb.id, targets=["p2"])
    mana(s, C=4)
    act(s, "p1", type="cast_spell", card_id=fb.id, targets=["p2"])
    pass_until_stack_empty(s)
    assert s.state.players["p2"].life == 36
    assert card(s, "Firebolt").zone == "p1:exile"  # exiled instead of going back to the graveyard
    assert not s.state.rules.flashback
    replay_matches(s)


def test_no_flashback_no_casting_from_the_graveyard(cards):
    s = build(cards)
    bolt = card(s, "Lightning Bolt")
    act(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "graveyard"})
    mana(s, R=1)
    with pytest.raises(ActionError, match="from your hand"):
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])


def test_flashback_card_is_offered_as_castable(cards):
    s = build(cards)
    fb = card(s, "Firebolt")
    act(s, "p1", type="move", card_ids=[fb.id], to={"zone": "graveyard"})
    mana(s, R=1, C=4)
    assert fb.id in hints(s.state, "p1", cards)["castable"]
