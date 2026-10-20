"""Lazy native prefixes preserve choices and JSON without spending global pools."""
from __future__ import annotations

import json

import pytest

from app.rules import prevention_frontier_discovery as lazy
from tests.test_rules_damage_rider_continuations import cards as cards
from tests.test_rules_prevention_frontier_grounding import record, setup


def test_lazy_native_opposite_orders_do_not_spend_other_rows(cards):
    plan, frame, events = setup(cards)
    before = plan.state.model_dump_json()
    draft = lazy.Draft.loads(lazy.start(plan, events).dumps())
    a, b = (p.id for p in frame.pools)
    assert {c.id for c in lazy.choices(plan, draft, 'left')} == {a, b}
    assert {c.id for c in lazy.choices(plan, draft, 'right')} == {a, b}
    draft = lazy.advance(plan, draft, 'left', a, amount=3)
    # Even a provisional exhaustion cannot steal the other affected player's choices.
    assert {c.id for c in lazy.choices(plan, draft, 'right')} == {a, b}
    draft = lazy.advance(plan, draft, 'right', b, amount=2)
    assert {c.id for c in lazy.choices(plan, draft, 'left')} == {b}
    assert {c.id for c in lazy.choices(plan, draft, 'right')} == {a}
    saved = lazy.Draft.loads(draft.dumps())
    assert saved == draft and plan.state.model_dump_json() == before
    assert [p.candidate for p in draft.picks] == [a, b]
    assert [json.loads(x.event)['amount'] for x in draft.leaves] == [1, 2]


def test_redirect_child_native_chooser_source_and_inherited_ids(cards):
    plan, frame, events = setup(cards, redirects=True)
    draft = lazy.start(plan, events)
    a, b = (p.id for p in frame.pools)
    draft = lazy.advance(plan, draft, 'left', a, amount=2)
    child = next(x for x in draft.leaves if x.id not in ('left', 'right'))
    event = json.loads(child.event)
    assert child.chooser == 'p2' and event['target'] == 'p2'
    assert event['source_oid'] == events[0]['source_oid'] and event['src'] == events[0]['src']
    assert a in event['applied'] and {c.id for c in lazy.choices(plan, draft, child.id)} == {b}
    draft = lazy.advance(plan, draft, child.id, b, amount=1)
    grandchild = next(x for x in draft.leaves if x.id not in ('left', 'right', child.id))
    event = json.loads(grandchild.event)
    assert grandchild.chooser == 'p1' and {a, b} <= set(event['applied'])
    assert lazy.choices(plan, draft, grandchild.id) == ()
    assert lazy.Draft.loads(draft.dumps()) == draft


def test_finite_prefix_needs_exact_numeric_row_and_legal_native_candidate(cards):
    plan, frame, events = setup(cards)
    draft = lazy.start(plan, events)
    a = frame.pools[0].id
    for n in (None, -1, 4, True):
        with pytest.raises(ValueError, match='exact legal numeric'):
            lazy.advance(plan, draft, 'left', a, amount=n)
    with pytest.raises(ValueError, match='legal native'):
        lazy.advance(plan, draft, 'left', 'invented', amount=1)


def test_stale_candidate_recipient_and_unknown_relevant_operation_reject(cards):
    plan, frame, events = setup(cards)
    draft = lazy.start(plan, events)
    plan.rules.replacements[0]['op']['limit'] = 4
    with pytest.raises(ValueError, match='candidates changed'):
        lazy.choices(plan, draft, 'left')
    plan.rules.replacements[0]['op']['limit'] = 3
    target = plan.state.cards[frame.packets[1].recipient]
    target.controller = 'p3'
    with pytest.raises(ValueError, match='controller changed'):
        lazy.choices(plan, draft, 'right')
    target.controller = 'p2'
    record(plan, {'do': 'set', 'n': 1})
    current = lazy.start(plan, events)
    with pytest.raises(ValueError, match='Unsupported'):
        lazy.choices(plan, current, 'left')


def test_irrelevant_unsupported_operation_is_not_a_false_discovery_rejection(cards):
    plan, frame, events = setup(cards)
    record(plan, {'do': 'set', 'n': 1}, match={'to': {'pids': ['p3']}})
    draft = lazy.start(plan, events)
    assert len(lazy.choices(plan, draft, 'left')) == 2
    assert len(lazy.choices(plan, draft, 'right')) == 2


def test_json_frame_separates_affected_order_player_and_pool_allocation_player(cards):
    plan, frame, events = setup(cards)
    draft = lazy.start(plan, events)
    a = frame.pools[0].id  # controller p3; original affected player p1
    with pytest.raises(ValueError, match='affected player'):
        lazy.choose_order(plan, draft, 'left', a, 'p3')
    pending = lazy.choose_order(plan, draft, 'left', a, 'p1')
    assert pending.pending.order_player == 'p1' and pending.pending.allocation_player == 'p3'
    pending = lazy.Draft.loads(pending.dumps())
    assert pending.picks == () and pending.leaves == draft.leaves
    with pytest.raises(ValueError, match='pool controller'):
        lazy.choose_amount(plan, pending, 1, 'p1')
    with pytest.raises(ValueError, match='awaiting'):
        lazy.choose_order(plan, pending, 'right', a, 'p2')
    result = lazy.choose_amount(plan, pending, 1, 'p3')
    assert result.pending is None
    assert result.picks[-1].order_player == 'p1' and result.picks[-1].allocation_player == 'p3'
    assert json.loads(next(x for x in result.leaves if x.id == 'left').event)['amount'] == 3


def test_native_optional_candidate_cannot_disappear_from_supported_frontier(cards):
    plan, frame, events = setup(cards)
    record(plan, {'do': 'finite_prevention', 'limit': 3, 'allocate': True, 'prevention': True, 'optional': True})
    draft = lazy.start(plan, events)
    with pytest.raises(ValueError, match='Unsupported'):
        lazy.choices(plan, draft, 'left')
