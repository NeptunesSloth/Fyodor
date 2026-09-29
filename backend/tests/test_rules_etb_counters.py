"""614.1c: "~ enters with N counters on it" (including X)."""

from __future__ import annotations

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.game_helpers import act, deck, enable, zone
from tests.test_rules_effects import mana, pass_until_stack_empty, replay_matches


def build(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Endless One"), (1, "Spike Feeder"), (8, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="draw", count=2)
    return s


def cast(s, name, **kw):
    card = next(s.state.cards[c] for c in zone(s.state, "p1", "hand") if s.state.cards[c].name == name)
    act(s, "p1", type="cast_spell", card_id=card.id, **kw)
    pass_until_stack_empty(s)
    return s.state.cards[card.id]


def test_enters_with_a_fixed_number(cards):
    s = build(cards)
    mana(s, G=3)
    feeder = cast(s, "Spike Feeder")
    assert feeder.zone == "p1:battlefield" and feeder.counters.get("+1/+1") == 2  # a 0/0 that survives
    replay_matches(s)


def test_enters_with_x(cards):
    s = build(cards)
    mana(s, C=4)
    one = cast(s, "Endless One", x_value=4)
    assert one.zone == "p1:battlefield" and one.counters.get("+1/+1") == 4


def test_x_zero_dies(cards):
    s = build(cards)
    one = cast(s, "Endless One", x_value=0)
    assert one.zone == "p1:graveyard"
