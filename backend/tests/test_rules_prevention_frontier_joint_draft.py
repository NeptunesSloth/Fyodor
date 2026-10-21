"""Completed lazy native prefixes must pass joint constraints and native replay."""
from __future__ import annotations

from dataclasses import replace as changed

import pytest

from app.rules import prevention_frontier_discovery as lazy
from app.rules import prevention_frontier_joint_draft as joint
from app.rules import prevention_frontier_prototype as model
from tests.test_rules_damage_rider_continuations import cards as cards
from tests.test_rules_prevention_frontier_grounding import record, setup


def prefix(plan, events, rows):
    draft = lazy.start(plan, events)
    for leaf, candidate, amount in rows:
        draft = lazy.advance(plan, draft, leaf, candidate, amount=amount)
    return lazy.Draft.loads(draft.dumps())


def test_completed_opposite_native_orders_match_affine_exhaustive_and_receipts(cards):
    plan, frame, events = setup(cards)
    a, b = (p.id for p in frame.pools)
    before = plan.state.model_dump_json()
    draft = prefix(plan, events, [('left', a, 1), ('right', b, 1), ('left', b, 2), ('right', a, 2)])
    completed = joint.complete(plan, draft, batch='lazy-complete')
    assert completed.solution in model.solutions(completed.frontier)
    assert [e['amount'] for e in completed.grounded.events] == [1, 1]
    assert sum(r['amount'] for r in completed.grounded.receipts) == 6
    assert plan.state.model_dump_json() == before


def test_incomplete_and_overdrawn_global_native_drafts_are_rejected(cards):
    plan, frame, events = setup(cards)
    a, b = (p.id for p in frame.pools)
    incomplete = prefix(plan, events, [('left', a, 1)])
    with pytest.raises(ValueError, match='incomplete'):
        joint.complete(plan, incomplete, batch='incomplete')
    # Each row is locally legal; their global A allocation spends four of three.
    overdrawn = prefix(plan, events, [('left', a, 2), ('left', b, 1), ('right', b, 2), ('right', a, 2)])
    with pytest.raises(ValueError, match='global budget'):
        joint.complete(plan, overdrawn, batch='overdrawn')


def test_irrelevant_unsupported_candidate_does_not_prevent_native_grounding(cards):
    plan, frame, events = setup(cards)
    a, b = (p.id for p in frame.pools)
    record(plan, {'do': 'half'}, match={'to': {'pids': ['p3']}})
    draft = prefix(plan, events, [('left', a, 1), ('right', b, 1), ('left', b, 2), ('right', a, 2)])
    result = joint.complete(plan, draft, batch='unrelated')
    assert sum(e['amount'] for e in result.grounded.events) == 2


def test_saved_native_ownership_cannot_be_forged(cards):
    plan, frame, events = setup(cards)
    a, b = (p.id for p in frame.pools)
    draft = prefix(plan, events, [('left', a, 1), ('right', b, 1), ('left', b, 2), ('right', a, 2)])
    forged = changed(draft, picks=(changed(draft.picks[0], allocation_player='p1'), *draft.picks[1:]))
    with pytest.raises(ValueError, match='forged'):
        joint.complete(plan, forged, batch='forged')


def test_native_redirect_cycle_completed_lazily_matches_joint_and_grounded_solution(cards):
    import json

    plan, frame, events = setup(cards, redirects=True)
    a, b = (p.id for p in frame.pools)
    left_child = json.dumps(['left', a, 'p2', ''], separators=(',', ':'))
    right_child = json.dumps(['right', b, 'p1', ''], separators=(',', ':'))
    draft = prefix(plan, events, [('left', a, 2), ('right', b, 2),
                                  (left_child, b, 1), (right_child, a, 1), ('right', a, 0)])
    completed = joint.complete(plan, draft, batch='native-cyclic-redirect')
    assert completed.solution in model.solutions(completed.frontier)
    assert sum(e['amount'] for e in completed.grounded.events) == 8
    assert len(completed.grounded.events) == 6
    assert all(len(e.get('applied', [])) == len(set(e.get('applied', []))) for e in completed.grounded.events)


def test_grounding_rejects_relevant_native_optional_before_applicable_filter(cards):
    from app.rules import prevention_frontier_grounding as native
    from tests.test_rules_prevention_frontier_grounding import interior

    plan, frame, events = setup(cards)
    record(plan, {'do': 'finite_prevention', 'limit': 3, 'allocate': True, 'prevention': True, 'optional': True})
    with pytest.raises(ValueError, match='Unsupported'):
        native.ground(plan, native.capture(plan, frame, events), interior(frame))
