"""Crew (CR 702.122): tap untapped creatures with total power N or more; the Vehicle becomes an
artifact creature until end of turn (a layer-4 type-changing effect)."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.rules.casting import activatable
from tests.game_helpers import act, deck, turn_on
from tests.test_rules_combat import creature
from tests.test_rules_effects import pass_until_stack_empty, replay_matches, run_until


def setup(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Sky-Skiff"), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    s = GameSession(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False), cards=cards)
    skiff = next(c for c in s.state.cards.values() if c.name == "Sky-Skiff")
    act(s, "p1", type="move", card_ids=[skiff.id], to={"zone": "battlefield"})  # set up by hand, before automation
    return s, skiff


def test_crew_makes_it_a_creature_that_can_attack(cards):
    s, skiff = setup(cards)
    pilot = creature(s, "p1", "Pilot", "1/1")
    turn_on(s)
    act(s, "p1", type="pass_priority")  # → main 1
    assert {"card_id": skiff.id, "ability": 1} in activatable(s.state, "p1", cards)
    act(s, "p1", type="activate_ability", card_id=skiff.id, ability=1)  # "Crew 1"
    d = s.state.rules.decision
    assert d.kind == "choose_cards" and {o.id for o in d.options} == {pilot.id}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[pilot.id])
    assert s.state.cards[pilot.id].tapped
    pass_until_stack_empty(s)
    from app.rules.plan import Plan

    plan = Plan(s.state, "p1", cards, None)
    assert plan.ch(s.state.cards[skiff.id]).is_creature
    act(s, "p1", type="pass_priority")  # → combat
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": skiff.id, "target": "p2"}])
    run_until(s, lambda s: s.state.players["p2"].life < 40)
    assert s.state.players["p2"].life == 38
    replay_matches(s)


def test_not_enough_power_and_not_a_creature_before_crewing(cards):
    s, skiff = setup(cards)
    creature(s, "p1", "Weakling", "0/1")
    turn_on(s)
    act(s, "p1", type="pass_priority")
    assert not any(a["card_id"] == skiff.id for a in activatable(s.state, "p1", cards))
    with pytest.raises(ActionError, match="total power 1"):
        act(s, "p1", type="activate_ability", card_id=skiff.id, ability=1)


def test_crewed_until_end_of_turn(cards):
    s, skiff = setup(cards)
    creature(s, "p1", "Pilot", "1/1")
    turn_on(s)
    act(s, "p1", type="pass_priority")
    pilot = next(c for c in s.state.cards.values() if c.name == "Pilot")
    act(s, "p1", type="activate_ability", card_id=skiff.id, ability=1, crew=[pilot.id])
    pass_until_stack_empty(s)
    run_until(s, lambda s: s.state.turn.active_player == "p2")
    from app.rules.plan import Plan

    assert not Plan(s.state, "p1", cards, None).ch(s.state.cards[skiff.id]).is_creature
