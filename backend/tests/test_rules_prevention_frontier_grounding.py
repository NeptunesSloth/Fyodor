"""Isolated native-operation grounding; no live batch/frontier or card hooks."""
from __future__ import annotations

from dataclasses import replace as changed

import pytest

from app.rules import prevention_frontier_grounding as native
from app.rules import prevention_frontier_prototype as model
from app.rules import replace
from app.rules.plan import Plan
from tests.test_rules_damage_rider_continuations import cards as cards
from tests.test_rules_designations import put
from tests.test_rules_prevention_outcomes import game


def record(plan, op, *, controller='p3', match=None, label='Joint pool'):
    return 'r:' + replace.add_record(plan, event='damage', match=match or {}, op=op,
                                    controller=controller, source=None, source_card=None, label=label)['id']


def setup(cards, *, redirects=False, source_name='Grizzly Bears', target_name='Centaur Courser'):
    s = game(cards)
    source = put(s, source_name, 'battlefield', 'p2')
    target = put(s, target_name, 'battlefield', 'p2')
    plan = Plan(s.state.model_copy(deep=True), 'p3', cards, None)
    ids = []
    for destination, controller in (('p2', 'p3'), ('p1', 'p2')):
        op = ({'do': 'redirect', 'limit': 3, 'allocate': True, 'to': 'pid', 'pid': destination}
              if redirects else {'do': 'finite_prevention', 'limit': 3, 'allocate': True, 'prevention': True})
        op['rider'] = {'aggregation': 'batch', 'effects': [{'do': 'gain_life', 'who': 'you', 'n': {'ref_amount': 'prevented'}}]}
        ids.append(record(plan, op, controller=controller))
    operations = [model.Operation(i, 'pool', pool=i) for i in ids]
    packets = (
        model.Packet('left', plan.oid(source.id), 'p1', '', 'p1', 4, tuple(operations)),
        model.Packet('right', plan.oid(source.id), target.id, plan.oid(target.id), 'p2', 4, tuple(operations[::-1])),
    )
    pools = tuple(model.Pool(i, controller, 3, mode='redirect' if redirects else 'prevent',
                             destination=destination if redirects else '', destination_controller=destination if redirects else '',
                             recipients=(target.id, 'p1' if destination == 'p2' else 'p2') if redirects else ())
                  for i, controller, destination in zip(ids, ('p3', 'p2'), ('p2', 'p1'), strict=True))
    frame = model.Frontier('native-original-batch', packets, pools,
                           destination_traces=(model.LocalTrace('p1', 'p1', tuple(operations)),
                                               model.LocalTrace('p2', 'p2', tuple(operations[::-1]))) if redirects else ())
    source_info = replace.source_info(plan, source.id, plan.oid(source.id), plan.ch(plan.state.cards[source.id]), source.controller)
    events = [{'kind': 'damage', 'amount': p.amount, 'source_card': source.id, 'source_oid': p.source_oid,
               'src': source_info, 'target': p.recipient, 'target_oid': p.recipient_oid or None,
               '_damage_lineage': p.lineage, 'combat': False} for p in packets]
    return plan, frame, events


def interior(frame):
    wanted = {frame.pools[0].id: {'left': 1, 'right': 2}, frame.pools[1].id: {'left': 2, 'right': 1}}
    return next(s for s in model.solutions(frame)
                if all(dict(selection.vector) == wanted[__import__('json').loads(selection.pool_group)[0]] for selection in s.allocations))


def test_opposite_local_orders_replay_native_receipts_and_riders_without_commit(cards):
    plan, frame, events = setup(cards)
    before = plan.state.model_dump_json()
    saved = native.Snapshot.loads(native.capture(plan, frame, events).dumps())
    result = native.ground(plan, saved, interior(frame))
    assert [e['amount'] for e in result.events] == [1, 1]
    assert sum(r['amount'] for r in result.receipts) == 6
    assert {r['controller'] for r in result.receipts} == {'p2', 'p3'}
    assert all(r['source_oid'] == events[0]['source_oid'] and r['source'] == events[0]['src'] for r in result.receipts)
    assert all(len(e['riders']) == 2 and e['src'] == events[0]['src'] for e in result.events)
    assert all(result.shields['limited:' + pool.id] == 0 for pool in frame.pools)
    assert plan.state.model_dump_json() == before
    assert all(plan.state.players[p].life == 40 for p in plan.live())
    # Packet traversal does not select the allocation or alter native receipts.
    assert native.ground(plan, saved, interior(frame), reverse=True) == result


def test_complete_joint_solution_cannot_be_forged_or_partially_supplied(cards):
    plan, frame, events = setup(cards)
    saved = native.capture(plan, frame, events)
    solved = interior(frame)
    with pytest.raises(ValueError, match='proved solution'):
        native.ground(plan, saved, changed(solved, residuals=(('left', 0), ('right', 2))))
    with pytest.raises((ValueError, KeyError)):
        native.ground(plan, saved, changed(solved, allocations=solved.allocations[:1]))


def test_native_candidate_changes_and_amount_dependent_operations_are_rejected(cards):
    plan, frame, events = setup(cards)
    saved = native.capture(plan, frame, events)
    plan.rules.replacements[0]['op']['limit'] = 4
    with pytest.raises(ValueError, match='changed'):
        native.ground(plan, saved, interior(frame))
    plan.rules.replacements[0]['op']['limit'] = 3
    record(plan, {'do': 'half'}, label='Unsupported half')
    with pytest.raises(ValueError, match='Unsupported'):
        native.ground(plan, native.capture(plan, frame, events), interior(frame))


def test_missing_applicable_native_candidate_and_changed_recipient_predicate_are_rejected(cards):
    plan, frame, events = setup(cards)
    record(plan, {'do': 'mul', 'n': 2}, label='Omitted multiplier')
    with pytest.raises(ValueError, match='missing'):
        native.ground(plan, native.capture(plan, frame, events), interior(frame))
    plan.rules.replacements.pop()
    plan.rules.replacements[0]['match'] = {'to': {'pids': ['p3']}}
    with pytest.raises(ValueError, match='predicate'):
        native.ground(plan, native.capture(plan, frame, events), interior(frame))


def test_native_redirect_children_keep_original_source_and_deduplicate_prior_receipts(cards):
    plan, frame, events = setup(cards, redirects=True)
    # Exhaustive oracle supplies a valid whole cyclic redirect allocation. The
    # adapter invokes actual source_shields.redirect, not a model-only terminal.
    for solved in model.solutions(frame):
        result = native.ground(plan, native.capture(plan, frame, events), solved)
        assert sum(e['amount'] for e in result.events) == 8
        assert all(e['source_oid'] == events[0]['source_oid'] and e['src'] == events[0]['src'] for e in result.events)
        assert not result.receipts


def test_source_batch_pool_has_no_accidental_live_native_key(cards):
    plan, frame, events = setup(cards)
    frame = changed(frame, pools=tuple(changed(p, scope='source_batch') for p in frame.pools))
    with pytest.raises(ValueError, match='Source-batch'):
        native.ground(plan, native.capture(plan, frame, events), interior(frame))


@pytest.mark.parametrize('before', [False, True])
def test_actual_furnace_local_order_is_grounded_through_native_multiplier(cards, before):
    plan, frame, events = setup(cards)
    furnace = next(c for c in plan.state.cards.values() if c.name == 'Furnace of Rath' and c.owner == 'p2')
    plan.do({'type': 'move', 'card_ids': [furnace.id], 'to': {'player': 'p2', 'zone': 'battlefield'}}, actor='p2')
    candidate = next(c for c in replace.damage_candidates(plan) if c.source_card == furnace.id)
    multiply = model.Operation(candidate.id, 'multiply', factor=2)
    frame = changed(frame, packets=tuple(changed(p, operations=(multiply, *p.operations) if before else (*p.operations, multiply))
                                         for p in frame.packets))
    solved = model.solutions(frame)[0]
    result = native.ground(plan, native.capture(plan, frame, events), solved)
    assert sum(e['amount'] for e in result.events) == (10 if before else 4)
    assert sum(r['amount'] for r in result.receipts) == 6


def test_native_protection_prevents_before_pools_without_false_pool_spending(cards):
    plan, frame, events = setup(cards, source_name='White Knight', target_name='Black Knight')
    target = frame.packets[1].recipient
    protection = next(c for c in replace.damage_candidates(plan) if c.op.get('protection_target') == target)
    right = changed(frame.packets[1], operations=(model.Operation(protection.id, 'protection'), *frame.packets[1].operations))
    frame = changed(frame, packets=(frame.packets[0], right))
    solved = model.solutions(frame)[0]
    result = native.ground(plan, native.capture(plan, frame, events), solved)
    assert sum(e['amount'] for e in result.events) == 0
    assert sum(r['amount'] for r in result.receipts) == 8
    assert next(r for r in result.receipts if r['candidate'] == protection.id)['amount'] == 4


def test_native_unpreventable_packets_do_not_consume_proved_pool_or_emit_receipts(cards):
    plan, frame, events = setup(cards)
    for event in events:
        event['unpreventable'] = True
    frame = changed(frame, packets=tuple(changed(p, unpreventable=True) for p in frame.packets))
    solved, = model.solutions(frame)
    result = native.ground(plan, native.capture(plan, frame, events), solved)
    assert sum(e['amount'] for e in result.events) == 8 and not result.receipts
    assert all('limited:' + p.id not in result.shields for p in frame.pools)


def test_changed_native_recipient_controller_is_not_trusted_from_saved_frame(cards):
    plan, frame, events = setup(cards)
    saved = native.capture(plan, frame, events)
    plan.state.cards[frame.packets[1].recipient].controller = 'p3'
    with pytest.raises(ValueError, match='identity, chooser'):
        native.ground(plan, saved, interior(frame))


def test_native_zero_budget_pool_is_not_applied_or_consumed(cards):
    plan, frame, events = setup(cards)
    for record in plan.rules.replacements:
        record['op']['limit'] = 0
    frame = changed(frame, pools=tuple(changed(p, remaining=0) for p in frame.pools))
    solved, = model.solutions(frame)
    result = native.ground(plan, native.capture(plan, frame, events), solved)
    assert sum(e['amount'] for e in result.events) == 8
    assert not result.receipts and not result.shields


def test_grounding_cannot_override_an_already_approved_pool_selection(cards):
    plan, frame, events = setup(cards)
    approved = interior(frame)
    frame = changed(frame, selections=approved.allocations[:1])
    other = next(s for s in model.solutions(changed(frame, selections=())) if s.allocations[0] != approved.allocations[0])
    with pytest.raises(ValueError, match='approved selection'):
        native.ground(plan, native.capture(plan, frame, events), other)


def test_native_original_source_lki_survives_departure_and_new_incarnation(cards):
    plan, frame, events = setup(cards)
    saved = native.capture(plan, frame, events)
    source = events[0]['source_card']
    plan.do({'type': 'move', 'card_ids': [source], 'to': {'player': 'p2', 'zone': 'graveyard'}}, actor='p2')
    plan.do({'type': 'move', 'card_ids': [source], 'to': {'player': 'p2', 'zone': 'battlefield'}}, actor='p2')
    assert plan.oid(source) != events[0]['source_oid']
    result = native.ground(plan, saved, interior(frame))
    assert all(r['source_oid'] == events[0]['source_oid'] and r['source'] == events[0]['src'] for r in result.receipts)


def test_native_original_recipient_cannot_be_replaced_with_new_incarnation(cards):
    plan, frame, events = setup(cards)
    saved = native.capture(plan, frame, events)
    target = frame.packets[1].recipient
    plan.do({'type': 'move', 'card_ids': [target], 'to': {'player': 'p2', 'zone': 'graveyard'}}, actor='p2')
    plan.do({'type': 'move', 'card_ids': [target], 'to': {'player': 'p2', 'zone': 'battlefield'}}, actor='p2')
    with pytest.raises(ValueError, match='incarnation'):
        native.ground(plan, saved, interior(frame))


def test_native_prevention_before_redirect_split_emits_one_deduplicated_receipt(cards):
    plan, frame, events = setup(cards)
    plan.rules.replacements[0]['op']['limit'] = 1
    plan.rules.replacements[1]['op'] = {'do': 'redirect', 'limit': 1, 'allocate': True, 'to': 'pid', 'pid': 'p2'}
    first = changed(frame.pools[0], remaining=1)
    second = changed(frame.pools[1], remaining=1, mode='redirect', destination='p2', destination_controller='p2')
    frame = changed(frame, packets=frame.packets[:1], pools=(first, second),
                    destination_traces=(model.LocalTrace('p2', 'p2', frame.packets[0].operations),))
    solved, = model.solutions(frame)
    result = native.ground(plan, native.capture(plan, frame, events[:1]), solved)
    assert sum(e['amount'] for e in result.events) == 3
    assert len(result.receipts) == 1 and result.receipts[0]['amount'] == 1
    assert all(len(e['prevention_receipts']) == 1 and len(e['riders']) == 1 for e in result.events)
    assert len({e['riders'][0]['receipt'] for e in result.events}) == 1
