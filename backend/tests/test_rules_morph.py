"""Morph and megamorph (CR 702.37): cast face down as a nameless 2/2 for {3}; turn it face up
for its morph cost as a special action. Nobody else learns what it is until then."""

from __future__ import annotations

import json

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules.plan import Plan
from tests.game_helpers import act, deck, enable
from tests.test_rules_effects import mana, pass_until_stack_empty


def build(cards, name):
    alice = deck(cards, "Krenko, Mob Boss", [(1, name), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")
    card = next(c for c in s.state.cards.values() if c.name == name)
    act(s, "p1", type="move", card_ids=[card.id], to={"zone": "hand"})
    return s, card


def test_cast_face_down_hides_it_then_turn_face_up(cards):
    s, slinger = build(cards, "Gravel Slinger")
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=slinger.id, face_down=True)
    pass_until_stack_empty(s)
    c = s.state.cards[slinger.id]
    assert c.zone == "p1:battlefield" and c.face_down
    assert Plan(s.state, "p1", cards, None).ch(c).pt == (2, 2)
    bob_view = json.dumps(s.view("p2"))
    assert "Gravel Slinger" not in bob_view and slinger.card_id not in bob_view  # not in cards, log or rules view
    assert "Gravel Slinger" in json.dumps(s.view("p1"))  # its controller may look at it
    with pytest.raises(ActionError, match="Not enough mana"):
        act(s, "p1", type="turn_face_up", card_id=slinger.id)
    mana(s, W=1, C=1)
    act(s, "p1", type="turn_face_up", card_id=slinger.id)
    c = s.state.cards[slinger.id]
    assert not c.face_down and Plan(s.state, "p1", cards, None).ch(c).pt == (1, 3)


def test_megamorph_adds_a_counter(cards):
    s, bow = build(cards, "Aerie Bowmasters")
    mana(s, C=3)
    act(s, "p1", type="cast_spell", card_id=bow.id, face_down=True)
    pass_until_stack_empty(s)
    mana(s, G=1, C=5)
    act(s, "p1", type="turn_face_up", card_id=bow.id)
    c = s.state.cards[bow.id]
    assert not c.face_down and c.counters.get("+1/+1") == 1
    assert Plan(s.state, "p1", cards, None).ch(c).pt == (4, 5)


def test_no_morph_no_face_down_cast(cards):
    s, _ = build(cards, "Gravel Slinger")
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "hand"})
    mana(s, C=3)
    with pytest.raises(ActionError, match="morph"):
        act(s, "p1", type="cast_spell", card_id=forest.id, face_down=True)
