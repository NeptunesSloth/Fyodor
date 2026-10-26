"""Wave 110A: Zilortha, Strength Incarnate (120.6, 704.5g, 702.19b; ruling 2020-04-17: power instead of toughness for lethal damage, 0 power needs 1 damage)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.wave110a_kit import *

ZIL = "Zilortha, Strength Incarnate"
CUTTER, WALL = "Goblin Heelcutter", "Wall of Blossoms"  # 3/2 (power above toughness) and 0/4 (power below)


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


def _shock(cards, victim, zil_owner, victim_owner="p1"):
    s = build(cards, [ZIL, victim, "Shock"], [ZIL, victim])
    if zil_owner:
        put(s, ZIL, zil_owner)
    v = put(s, victim, victim_owner)
    cast(s, "Shock", [v.id])
    answer(s)
    return s, v


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(ZIL)).level == "FULL"


@pytest.mark.parametrize(("zil_owner", "dies"), [(None, True), ("p1", False), ("p2", True)])
def test_lethal_damage_to_a_power_above_toughness_creature(cards, zil_owner, dies):
    s, v = _shock(cards, CUTTER, zil_owner)  # 2 damage to a 3/2: lethal by toughness, not by power 3 (only for its controller)
    assert s.state.cards[v.id].zone.endswith("graveyard") == dies
    check(s)


@pytest.mark.parametrize(("zil_owner", "dies"), [(None, False), ("p1", True), ("p2", False)])
def test_a_zero_power_creature_dies_to_one_damage_marked(cards, zil_owner, dies):
    s, v = _shock(cards, WALL, zil_owner)  # 2 damage to a 0/4: lethal by power 0 only with at least 1 damage marked
    assert s.state.cards[v.id].zone.endswith("graveyard") == dies
    check(s)


def test_zilortha_herself_survives_damage_below_her_power(cards):
    s = build(cards, [ZIL, "Shock"])
    z = put(s, ZIL)
    cast(s, "Shock", [z.id])
    answer(s)
    assert s.state.cards[z.id].zone == "p1:battlefield"  # 7/3 takes 2 and 3 toughness would not have died either; the next one shows the power rule
    cast(s, "Shock", [z.id])
    answer(s)
    assert s.state.cards[z.id].zone == "p1:battlefield"  # 4 damage on a 7/3: lethal by power only at 7
    check(s)


def test_damage_becomes_lethal_again_when_zilortha_leaves(cards):
    s, v = _shock(cards, CUTTER, "p1")
    assert s.state.cards[v.id].zone == "p1:battlefield" and s.state.cards[v.id].damage == 2
    act(s, "p1", type="move", card_ids=[card_named(s, ZIL).id], to={"player": "p1", "zone": "graveyard"})
    cast(s, "Shock", ["p2"])  # any later action: state-based actions see 2 damage on a 3/2 once she is gone (ruling: nonlethal damage may become lethal)
    answer(s)
    assert s.state.cards[v.id].zone.endswith("graveyard")


@pytest.mark.parametrize(("p2_zilortha", "through"), [(False, 5), (True, 4)])
def test_trample_assigns_lethal_by_power_to_a_blocker_its_controller_protects(cards, p2_zilortha, through):  # 702.19b
    s = build(cards, [ZIL], [ZIL, CUTTER])
    attacker = put(s, ZIL)
    if p2_zilortha:
        put(s, ZIL, "p2")
    blocker = put(s, CUTTER, "p2")
    next_turn(s)
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": attacker.id, "target": "p2"}])
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": blocker.id, "attacker_id": attacker.id}])
    before = life(s, "p2")
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.kind == "divide":
            lethal = (d.resume or {}).get("lethal")
            act(s, d.player, type="choose", decision_id=d.id, amounts=[lethal[0], 7 - lethal[0]])  # exactly lethal to the blocker, the rest tramples over
        elif d is not None:
            answer(s)
        elif s.state.turn.phase in ("combat_damage", "declare_blockers"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert before - life(s, "p2") == through
