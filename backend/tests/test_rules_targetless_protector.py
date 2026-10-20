"""Native protector-change action serialization, paired with actual Battle casting/attack."""

from __future__ import annotations

from app.rules import battles
from app.rules.plan import Plan
from tests.test_rules_defender_relative36 import cards as cards
from tests.test_rules_designations import roundtrip, settle
from tests.test_rules_targetless_attackers import battle_setup


def test_native_protector_change_records_targetless_state_and_replays(cards):
    s, source, battle = battle_setup(cards)
    plan = Plan(s.state.model_copy(deep=True), "p1", cards, None)
    battles.set_protector(plan, plan.state.cards[battle.id], "p3")
    plan.do({"type": "rules_sync", "rules": plan.rules.model_dump(mode="json")})
    for action in plan.steps:
        s.perform(action.get("actor") or "p1", action, trusted=True)
    assert battles.protector(s.state, s.state.cards[battle.id]) == "p3"
    assert s.state.cards[source.id].is_attacking
    assert s.state.cards[source.id].attacking_without_target == "p2"
    assert s.state.cards[source.id].attack_defender_lost
    settle(s)
    assert s.state.rules.decision is None
    roundtrip(s)
