"""Unregistered source/lineage-specific 616 traces agree across all proof engines."""
from __future__ import annotations

import json
from dataclasses import replace as changed

import pytest

from app.rules import prevention_frontier_constraints as affine
from app.rules import prevention_frontier_grounding as native
from app.rules import prevention_frontier_prototype as model
from app.rules import replace
from tests.test_rules_damage_rider_continuations import cards as cards
from tests.test_rules_prevention_frontier_grounding import record, setup


def test_redirected_white_and_green_sources_use_different_native_protection_traces(cards):
    plan, original, events = setup(cards, source_name='White Knight', target_name='Black Knight')
    plan.rules.replacements.clear()
    target = original.packets[1].recipient
    ident = record(plan, {'do': 'redirect', 'limit': 4, 'allocate': True, 'to': 'oid', 'oid': plan.oid(target)})
    green = next(c for c in plan.state.cards.values() if c.name == 'Grizzly Bears' and c.owner == 'p2')
    plan.do({'type': 'move', 'card_ids': [green.id], 'to': {'player': 'p2', 'zone': 'battlefield'}}, actor='p2')
    green = plan.state.cards[green.id]
    white = events[0]['source_oid']
    green_oid = plan.oid(green)
    protection = next(c for c in replace.damage_candidates(plan) if c.op.get('protection_target') == target)
    operation = model.Operation(ident, 'pool', pool=ident)
    frame = model.Frontier('native-colors', (
        model.Packet('white', white, 'p1', '', 'p1', 2, (operation,)),
        model.Packet('green', green_oid, 'p1', '', 'p1', 2, (operation,)),
    ), (model.Pool(ident, 'p3', 4, mode='redirect', destination=target, destination_oid=plan.oid(target),
                   destination_controller='p2', recipients=('p1',)),), destination_traces=(
        model.LocalTrace(target, 'p2', (model.Operation(protection.id, 'protection'),), source_oid=white),
        model.LocalTrace(target, 'p2', (), source_oid=green_oid),
    ))
    source_info = replace.source_info(plan, green.id, green_oid, plan.ch(green), green.controller)
    events = [{**events[0], 'amount': 2, '_damage_lineage': 'white'},
              {**events[0], 'amount': 2, 'source_card': green.id, 'source_oid': green_oid,
               'src': source_info, '_damage_lineage': 'green'}]
    frame = model.Frontier.loads(frame.dumps())
    solved, = model.solutions(frame)
    assert affine.witness(frame) == solved
    result = native.ground(plan, native.capture(plan, frame, events), solved)
    assert sum(e['amount'] for e in result.events) == 2
    assert len(result.receipts) == 1 and result.receipts[0]['source_oid'] == white
    assert result.receipts[0]['amount'] == 2
    assert result.shields['redir:' + ident] == 0  # one shared4 pool, not a pool per source


def lineage_cycle(cards):
    plan, initial, events = setup(cards)
    for current_record in plan.rules.replacements:
        current_record['match'] = {'to': {'pids': ['p2']}}
    redirect = record(plan, {'do': 'redirect', 'limit': 8, 'allocate': True, 'to': 'pid', 'pid': 'p2'},
                      controller='p1', match={'to': {'pids': ['p1']}})
    a, b = initial.pools
    def pool_op(ident):
        return model.Operation(ident, 'pool', pool=ident)
    source = initial.packets[0].source_oid
    left = json.dumps(['left', redirect, 'p2', ''], separators=(',', ':'))
    right = json.dumps(['right', redirect, 'p2', ''], separators=(',', ':'))
    frame = model.Frontier('native-lineages', (
        model.Packet('left', source, 'p1', '', 'p1', 4, (pool_op(redirect),)),
        model.Packet('right', source, 'p1', '', 'p1', 4, (pool_op(redirect),)),
    ), (changed(a, recipients=('p2',)), changed(b, recipients=('p2',)),
        model.Pool(redirect, 'p1', 8, mode='redirect', recipients=('p1',), destination='p2', destination_controller='p2')),
        destination_traces=(
            model.LocalTrace('p2', 'p2', (pool_op(a.id), pool_op(b.id))),  # Explicit legacy wildcard fallback.
            model.LocalTrace('p2', 'p2', (pool_op(a.id), pool_op(b.id)), source_oid=source, lineage=left),
            model.LocalTrace('p2', 'p2', (pool_op(b.id), pool_op(a.id)), source_oid=source, lineage=right),
        ))
    events = [{**events[0], '_damage_lineage': row} for row in ('left', 'right')]
    wanted = {a.id: {left: 1, right: 2}, b.id: {left: 2, right: 1}, redirect: {'left': 4, 'right': 4}}
    solved = next(s for s in model.solutions(frame)
                  if all(dict(sel.vector) == wanted[json.loads(sel.pool_group)[0]] for sel in s.allocations))
    return plan, frame, events, solved


def test_same_source_same_recipient_distinct_lineages_own_opposite_616_orders_and_shared_budgets(cards):
    plan, frame, events, solved = lineage_cycle(cards)
    prefix = tuple((sel.pool_group, row, n) for sel in solved.allocations for row, n in sel.vector)
    assert affine.witness(frame, prefix) == solved
    result = native.ground(plan, native.capture(plan, frame, events), solved)
    assert [e['amount'] for e in result.events] == [1, 1]
    assert sum(r['amount'] for r in result.receipts) == 6
    assert native.ground(plan, native.capture(plan, frame, events), solved, reverse=True) == result
    assert all(result.shields['limited:' + p.id] == 0 for p in frame.pools[:2])


@pytest.mark.parametrize('bad', ['unknown_source', 'unknown_lineage', 'ambiguous', 'duplicate'])
def test_unknown_stale_or_ambiguous_trace_selectors_are_rejected(cards, bad):
    _, frame, _, _ = lineage_cycle(cards)
    traces = list(frame.destination_traces)
    if bad == 'unknown_source':
        traces[1] = changed(traces[1], source_oid='source.new-unknown')
    elif bad == 'unknown_lineage':
        traces[1] = changed(traces[1], lineage='stale-branch')
    elif bad == 'ambiguous':
        traces[1] = changed(traces[1], source_oid='')
        traces.append(changed(traces[2], lineage=''))
    else:
        traces.append(traces[1])
    frame = changed(frame, destination_traces=tuple(traces))
    with pytest.raises(ValueError, match='Unknown|stale|Ambiguous|Duplicate'):
        model.solutions(frame)
    with pytest.raises(ValueError, match='Unknown|stale|Ambiguous|Duplicate'):
        affine.witness(frame)


def test_legacy_json_destination_trace_defaults_remain_explicit_wildcards(cards):
    _, frame, _, _ = lineage_cycle(cards)
    raw = json.loads(changed(frame, destination_traces=frame.destination_traces[:1]).dumps())
    for trace in raw['destination_traces']:
        del trace['source_oid']
        del trace['lineage']
    restored = model.Frontier.loads(json.dumps(raw))
    assert restored.destination_traces[0].source_oid == restored.destination_traces[0].lineage == ''
    assert model.solutions(restored)
    assert affine.witness(restored) in model.solutions(restored)
