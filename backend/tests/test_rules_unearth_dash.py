"""Unearth (702.84) and dash (702.109): haste, a delayed "next end step" trigger, and unearth's
"exile it instead if it would leave the battlefield" replacement."""

from __future__ import annotations

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules.plan import Plan
from tests.game_helpers import act, deck, enable
from tests.test_rules_effects import mana, pass_until_stack_empty
from tests.test_rules_suspend import until


def build(cards, name, zone):
    alice = deck(cards, "Krenko, Mob Boss", [(1, name), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")
    card = next(c for c in s.state.cards.values() if c.name == name)
    act(s, "p1", type="move", card_ids=[card.id], to={"zone": zone})
    return s, card


def haste(s, cards, card):
    return "haste" in Plan(s.state, "p1", cards, None).ch(s.state.cards[card.id]).keywords


def test_unearth_returns_with_haste_then_is_exiled_at_end_step(cards):
    s, zombie = build(cards, "Dregscape Zombie", "graveyard")
    mana(s, B=1)
    act(s, "p1", type="activate_ability", card_id=zombie.id, ability=0)
    pass_until_stack_empty(s)
    assert s.state.cards[zombie.id].zone == "p1:battlefield" and haste(s, cards, zombie)
    until(s, lambda s: s.state.cards[zombie.id].zone != "p1:battlefield")
    assert s.state.cards[zombie.id].zone == "p1:exile"


def test_unearthed_creature_that_dies_is_exiled_instead(cards):
    s, zombie = build(cards, "Dregscape Zombie", "graveyard")
    mana(s, B=1)
    act(s, "p1", type="activate_ability", card_id=zombie.id, ability=0)
    pass_until_stack_empty(s)
    act(s, "p1", type="set_damage", card_ids=[zombie.id], value=1)
    act(s, "p1", type="pass_priority")  # state-based actions: lethal damage
    assert s.state.cards[zombie.id].zone == "p1:exile"


def test_dash_haste_and_back_to_hand(cards):
    s, scout = build(cards, "Mardu Scout", "hand")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=scout.id, dash=True)
    pass_until_stack_empty(s)
    assert s.state.cards[scout.id].zone == "p1:battlefield" and haste(s, cards, scout)
    until(s, lambda s: s.state.cards[scout.id].zone != "p1:battlefield")
    assert s.state.cards[scout.id].zone == "p1:hand"
