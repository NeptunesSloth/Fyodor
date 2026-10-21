"""Lazy native future orders are witnessed jointly rather than eagerly enumerated."""
from __future__ import annotations

from dataclasses import replace as changed

import pytest

from app.rules import prevention_frontier_prototype as model
from app.rules import prevention_frontier_symbolic as symbolic
from tests.test_rules_damage_rider_continuations import cards as cards
from tests.test_rules_prevention_frontier_grounding import record, setup


def test_lazy_symbolic_witness_is_native_and_can_freeze_opposite_local_orders(cards):
    plan, frame, events = setup(cards)
    before = plan.state.model_dump_json()
    result = symbolic.witness(plan, events, batch='symbolic')
    assert result is not None and result.solution in model.solutions(result.layout.frontier)
    a, b = (p.id for p in frame.pools)
    roots = [o for o in result.layout.orders if __import__('json').loads(o.key)[1] in ('left', 'right') and not __import__('json').loads(o.key)[4]]
    fixed = tuple(changed(o, selected=a if __import__('json').loads(o.key)[1] == 'left' else b) for o in roots)
    opposite = symbolic.witness(plan, events, batch='symbolic', orders=fixed)
    assert opposite is not None
    assert opposite.layout.frontier.packets[0].operations[0].id == a
    assert opposite.layout.frontier.packets[1].operations[0].id == b
    assert plan.state.model_dump_json() == before


def test_symbolic_redirect_cycles_keep_source_and_native_chooser_lineages(cards):
    plan, frame, events = setup(cards, redirects=True)
    result = symbolic.witness(plan, events, batch='symbolic-redirect')
    assert result is not None
    assert sum(e['amount'] for e in result.grounded.events) == 8
    assert all(e['source_oid'] == events[0]['source_oid'] for e in result.grounded.events)
    assert {o.chooser for o in result.layout.orders} >= {'p1', 'p2'}
    assert result.solution in model.solutions(result.layout.frontier)


def test_symbolic_billion_damage_uses_integer_constraints_and_rejects_numeric_overdraw(cards):
    plan, frame, events = setup(cards)
    for event in events:
        event['amount'] = 10**9
    result = symbolic.witness(plan, events, batch='large')
    assert result is not None
    group, row, _ = model.rows(result.layout.frontier)[0]
    assert symbolic.witness(plan, events, batch='large', numeric=((group, row, 4),)) is None
    assert sum(e['amount'] for e in result.grounded.events) == 2 * 10**9 - 6


def test_unsupported_positive_native_operation_is_never_omitted(cards):
    plan, frame, events = setup(cards)
    record(plan, {'do': 'half'})
    # Eight damage cannot all be prevented by the two three-point pools.
    assert symbolic.witness(plan, events, batch='unsupported') is None


def test_unknown_future_replacement_can_only_be_bypassed_when_its_actual_event_is_zero(cards):
    plan, frame, events = setup(cards, redirects=True)
    for event in events:
        event['amount'] = 1
    plan.rules.replacements[1]['op'] = {'do': 'finite_prevention', 'limit': 3, 'allocate': True, 'prevention': True}
    plan.rules.replacements[1]['match'] = {}
    record(plan, {'do': 'half'}, match={'to': {'pids': ['p2']}})
    result = symbolic.witness(plan, events, batch='zero-only')
    assert result is not None and result.layout.zero_terminals
    assert sum(e['amount'] for e in result.grounded.events) == 0


def test_forged_native_order_owner_and_ambiguous_prefix_are_rejected(cards):
    plan, frame, events = setup(cards)
    result = symbolic.witness(plan, events, batch='owners')
    assert result is not None
    first = result.layout.orders[0]
    with pytest.raises(ValueError, match='chooser'):
        symbolic.witness(plan, events, batch='owners', orders=(changed(first, chooser='p3'),))
    with pytest.raises(ValueError, match='Ambiguous'):
        symbolic.witness(plan, events, batch='owners', orders=(first, first))
