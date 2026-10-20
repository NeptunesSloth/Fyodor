"""Confirmed native questions, separate owners and dependent numeric resets."""
from __future__ import annotations

import json
from dataclasses import replace as changed

import pytest

from app.rules import prevention_frontier_joint_draft as joint
from app.rules import prevention_frontier_journal as journal
from app.rules import prevention_frontier_symbolic as symbolic
from tests.test_rules_damage_rider_continuations import cards as cards
from tests.test_rules_prevention_frontier_grounding import record, setup


def finish(plan, frame):
    for _ in range(60):
        frame = journal.Frame.loads(frame.dumps())
        q = journal.question(plan, frame)
        if isinstance(q, joint.Completed):
            return frame, q
        if q.kind == 'order':
            frame = journal.choose_order(plan, frame, q.candidates[0], q.actor)
        else:
            witness = journal._witness(plan, frame)
            assert witness is not None
            value = next(n for selection in witness.solution.allocations if selection.pool_group == q.group
                         for row, n in selection.vector if row == q.leaf)
            frame = journal.choose_amount(plan, frame, value, q.actor)
    raise AssertionError('Small native joint fixture did not finish')


def test_actual_questions_separate_affected_order_and_native_pool_owner(cards):
    plan, frame, events = setup(cards)
    untouched = plan.state.model_dump_json()
    saved = journal.start(plan, events, batch='questions')
    q = journal.question(plan, saved)
    assert isinstance(q, journal.Question) and q.kind == 'order' and q.actor == 'p1'
    with pytest.raises(ValueError, match='affected player'):
        journal.choose_order(plan, saved, q.candidates[0], 'p3')
    saved = journal.choose_order(plan, saved, q.candidates[0], 'p1')
    q = journal.question(plan, saved)
    assert isinstance(q, journal.Question) and q.kind == 'amount' and q.actor == 'p3'
    with pytest.raises(ValueError, match='pool controller'):
        journal.choose_amount(plan, saved, 1, 'p1')
    with pytest.raises(ValueError, match='actual capacity'):
        journal.choose_amount(plan, saved, 4, 'p3')
    final, completed = finish(plan, saved)
    assert final.numeric and sum(e['amount'] for e in completed.grounded.events) == 2
    assert plan.state.model_dump_json() == untouched


def test_actual_redirect_questions_use_only_confirmed_positive_branches(cards):
    plan, frame, events = setup(cards, redirects=True)
    saved = journal.start(plan, events, batch='redirect-questions')
    final, completed = finish(plan, saved)
    assert sum(e['amount'] for e in completed.grounded.events) == 8
    assert any(n.row.startswith('[') for n in final.numeric)
    assert {t.affected_player for t in completed.frontier.destination_traces} >= {'p1', 'p2'}


def test_later_legal_order_resets_only_dependent_vectors_and_preserves_independent_pool(cards):
    plan, frame, events = setup(cards)
    a, b = (p.id for p in frame.pools)
    for rec in plan.rules.replacements:
        rec['match'] = {'to': {'pids': ['p1', 'p2']}}
    for event in events:
        event['amount'] = 2
    events[1].update(target='p2', target_oid=None)
    events.append({**events[0], 'target': 'p3', 'target_oid': None, '_damage_lineage': 'third'})
    c = record(plan, {'do': 'finite_prevention', 'limit': 1, 'allocate': True, 'prevention': True},
               controller='p2', match={'to': {'pids': ['p3']}})
    saved = journal.start(plan, events, batch='reset')
    old = symbolic.witness(plan, events, batch='reset')
    assert old is not None
    right = next(o for o in old.layout.orders if json.loads(o.key)[1] == 'right' and not json.loads(o.key)[4])
    def group(candidate):
        return json.dumps([candidate, 'reset', None], separators=(',', ':'))
    fixed = (journal.Number(group(a), 'left', 1, 'p3'), journal.Number(group(a), 'right', 2, 'p3'),
             journal.Number(group(b), 'left', 1, 'p2'), journal.Number(group(b), 'right', 0, 'p2'),
             journal.Number(group(c), 'third', 1, 'p2'))
    saved = changed(saved, orders=(changed(right, selected=a),), numeric=fixed)
    assert journal._witness(plan, saved) is not None
    q = journal.question(plan, saved)
    assert isinstance(q, journal.Question) and q.kind == 'order' and q.leaf == 'left'
    reset = journal.choose_order(plan, saved, b, 'p1')
    assert reset.numeric == (fixed[-1],)
    assert any(o.selected == b and json.loads(o.key)[1] == 'left' for o in reset.orders)
    final, completed = finish(plan, reset)
    assert fixed[-1] in final.numeric and sum(e['amount'] for e in completed.grounded.events) == 1


def test_stale_native_snapshots_and_forged_saved_number_ownership_fail_atomically(cards):
    plan, frame, events = setup(cards)
    saved = journal.start(plan, events, batch='stale')
    plan.rules.replacements[0]['op']['limit'] = 4
    with pytest.raises(ValueError, match='stale'):
        journal.question(plan, saved)
    plan.rules.replacements[0]['op']['limit'] = 3
    target = plan.state.cards[events[1]['target']]
    target.controller = 'p3'
    with pytest.raises(ValueError, match='stale'):
        journal.question(plan, saved)
    target.controller = 'p2'
    q = journal.question(plan, saved)
    saved = journal.choose_order(plan, saved, q.candidates[0], q.actor)
    q = journal.question(plan, saved)
    forged = changed(saved, numeric=(journal.Number(q.group, q.leaf, 1, 'p1'),))
    with pytest.raises(ValueError, match='forged'):
        journal.question(plan, forged)
