"""Pure, unregistered proof cases; these do not claim card support."""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from app.rules.prevention_frontier_prototype import (
    Frontier,
    LocalTrace,
    Operation,
    Packet,
    Pool,
    Selection,
    choose,
    group,
    invalidate,
    options,
    solutions,
)


def pool(ident):
    return Operation(ident, 'pool', pool=ident)


def cycle():
    return Frontier('original-batch', (
        Packet('left', 'source-1.old', 'p1', '', 'p1', 4, (pool('A'), pool('B'))),
        Packet('right', 'source-1.old', 'creature', 'creature.old', 'p2', 4, (pool('B'), pool('A'))),
    ), (Pool('A', 'p3', 3), Pool('B', 'p2', 3)))


def test_opposite_local_pool_orders_have_joint_interior_solutions_without_global_order():
    frame = cycle()
    a = group(frame, frame.pools[0], frame.packets[0])
    b = group(frame, frame.pools[1], frame.packets[0])
    interior = (Selection(a, (('left', 1), ('right', 2))), Selection(b, (('left', 2), ('right', 1))))
    matched = [s for s in solutions(frame) if s.allocations == interior]
    assert len(matched) == 1
    assert matched[0].residuals == (('left', 1), ('right', 1))
    # Swapping packet traversal does not change feasible choices or capacities.
    assert set(solutions(frame)) == set(solutions(replace(frame, packets=frame.packets[::-1])))


def test_controller_entitlement_is_separate_from_affected_players_and_choices_replan_jointly():
    frame = cycle()
    a = group(frame, frame.pools[0], frame.packets[0])
    b = group(frame, frame.pools[1], frame.packets[0])
    with pytest.raises(ValueError, match='allocation controller'):
        options(frame, a, 'p1')
    selected_a = Selection(a, (('left', 1), ('right', 2)))
    frame = choose(frame, selected_a, 'p3')
    frame = Frontier.loads(frame.dumps())
    assert frame.selections == (selected_a,)
    # B=(0,3) would leave capacity1 for A's required right2: reject it,
    # rather than consuming A or silently changing the affected player's order.
    assert Selection(b, (('left', 0), ('right', 3))) not in options(frame, b, 'p2')
    frame = choose(frame, Selection(b, (('left', 2), ('right', 1))), 'p2')
    assert len(solutions(frame)) == 1
    assert solutions(frame)[0].residuals == (('left', 1), ('right', 1))


@pytest.mark.parametrize('before,expected', [(True, 6), (False, 4)])
def test_multiplier_local_order_changes_capacity_and_residuals(before, expected):
    furnace = Operation('furnace', 'multiply', factor=2)
    ops = (furnace, pool('A')) if before else (pool('A'), furnace)
    frame = Frontier('batch', (Packet('row', 'source.old', 'p1', '', 'p1', 4, ops),), (Pool('A', 'p3', 2),))
    assert {s.residuals for s in solutions(frame)} == {(('row', expected),)}


def test_protection_and_unpreventable_do_not_spend_shared_budget():
    frame = Frontier('batch', (
        Packet('protected', 'old', 'c1', 'c1.old', 'p1', 4, (Operation('protection', 'protection'), pool('A'))),
        Packet('unpreventable', 'old', 'p1', '', 'p1', 4, (pool('A'),), unpreventable=True),
        Packet('ordinary', 'old', 'p2', '', 'p2', 4, (pool('A'),)),
    ), (Pool('A', 'p3', 3),))
    solved, = solutions(frame)
    assert solved.allocations[0].vector == (('ordinary', 3), ('protected', 0), ('unpreventable', 0))
    assert solved.residuals == (('ordinary', 1), ('protected', 0), ('unpreventable', 4))


def test_cover_style_budget_is_per_original_source_not_per_recipient():
    frame = Frontier('batch', tuple(
        Packet(row, source, recipient, oid, controller, amount, (pool('cover'),))
        for row, source, recipient, oid, controller, amount in (
            ('source1-blocker', 'source1.old', 'blocker', 'blocker.old', 'p1', 2),
            ('source1-player', 'source1.old', 'p1', '', 'p1', 2),
            ('source2-player', 'source2.old', 'p1', '', 'p1', 4),
        )
    ), (Pool('cover', 'p1', 2, scope='source_batch'),))
    solved = solutions(frame)
    assert len(solved) == 3  # source1 allows 0+2,1+1,2+0; source2 has its own2.
    assert all(sum(n for _, n in s.residuals) == 4 for s in solved)
    assert any(s.residuals == (('source1-blocker', 1), ('source1-player', 1), ('source2-player', 2)) for s in solved)


def test_original_source_oid_filter_does_not_follow_new_incarnation_and_zero_budget_is_valid():
    frame = Frontier('batch', (
        Packet('old', 'source.old', 'p1', '', 'p1', 2, (pool('A'),)),
        Packet('new', 'source.new', 'p1', '', 'p1', 2, (pool('A'),)),
    ), (Pool('A', 'p2', 7, source_oids=('source.old',)),))
    solved, = solutions(frame)
    assert solved.residuals == (('new', 2), ('old', 0))
    zero = replace(frame, pools=(replace(frame.pools[0], remaining=0),))
    assert solutions(zero)[0].residuals == (('new', 2), ('old', 2))


def test_saved_selection_that_loses_capacity_is_not_committed_or_silently_redistributed():
    frame = cycle()
    key = group(frame, frame.pools[0], frame.packets[0])
    frame = choose(frame, Selection(key, (('left', 3), ('right', 0))), 'p3')
    left = replace(frame.packets[0], operations=(Operation('protection', 'protection'), *frame.packets[0].operations))
    changed = replace(frame, packets=(left, frame.packets[1]))
    assert not solutions(changed)
    # The caller must invalidate the dependent vector and ask its owner again.
    refreshed = replace(changed, selections=())
    assert solutions(refreshed)
    assert all(s.vector != (('left', 3), ('right', 0)) for s in options(refreshed, key, 'p3'))


def test_shared_redirect_pool_splits_one_source_across_recipients_and_keeps_original_source():
    frame = Frontier('batch', (
        Packet('blocker', 'spell.old', 'creature', 'creature.old', 'p1', 2, (pool('A'),)),
        Packet('player', 'spell.old', 'p1', '', 'p1', 2, (pool('A'),), unpreventable=True),
    ), (Pool('A', 'p3', 2, mode='redirect', destination='p2', destination_controller='p2'),),
       destination_traces=(LocalTrace('p2', 'p2', ()),))
    key = group(frame, frame.pools[0], frame.packets[0])
    selected = choose(frame, Selection(key, (('blocker', 1), ('player', 1))), 'p3')
    selected = Frontier.loads(selected.dumps())
    solved, = solutions(selected)
    amounts = dict(solved.residuals)
    assert sum(amounts.values()) == 4
    assert sum(amounts[path] for path, _, recipient, _, _, _ in solved.terminals if recipient == 'p2') == 2
    assert amounts['blocker'] == amounts['player'] == 1
    assert all(source == 'spell.old' for _, source, _, _, _, _ in solved.terminals)
    assert all('A' in applied for _, _, _, _, _, applied in solved.terminals)


def test_redirect_destination_protection_has_its_own_affected_player_trace():
    frame = Frontier('batch', (Packet('row', 'source.old', 'p1', '', 'p1', 3, (pool('A'),)),),
                     (Pool('A', 'p3', 2, mode='redirect', destination='protected', destination_oid='protected.old',
                           destination_controller='p2'),),
                     destination_traces=(LocalTrace('protected', 'p2', (Operation('protection', 'protection'),)),))
    solved, = solutions(frame)
    amounts = dict(solved.residuals)
    assert amounts['row'] == 1
    redirected = next(t for t in solved.terminals if t[2] == 'protected')
    assert redirected[3:5] == ('protected.old', 'p2')
    assert amounts[redirected[0]] == 0
    assert solved.allocations[0].vector == (('row', 2),)


def redirect_cycle():
    return Frontier('batch', (
        Packet('left', 'source.old', 'p1', '', 'p1', 2, (pool('A'), pool('B'))),
        Packet('right', 'source.old', 'p2', '', 'p2', 2, (pool('B'), pool('A'))),
    ), (Pool('A', 'p3', 1, mode='redirect', recipients=('p1',), destination='p2', destination_controller='p2'),
        Pool('B', 'p2', 1, mode='redirect', recipients=('p2',), destination='p1', destination_controller='p1')),
        destination_traces=(LocalTrace('p1', 'p1', (pool('A'), pool('B'))),
                            LocalTrace('p2', 'p2', (pool('B'), pool('A')))))


def test_two_redirect_pools_can_return_damage_without_reapplying_candidates_or_creating_damage():
    frame = redirect_cycle()
    found = solutions(frame)
    assert found
    a = group(frame, frame.pools[0], frame.packets[0])
    b = group(frame, frame.pools[1], frame.packets[0])
    # A redirects original left damage; B redirects that child back to p1.
    # B's budget therefore cannot also redirect the original right packet.
    returned = next(s for s in found if dict(next(v.vector for v in s.allocations if v.pool_group == a))['left'] == 1
                    and dict(next(v.vector for v in s.allocations if v.pool_group == b))['right'] == 0)
    assert all(sum(n for _, n in s.residuals) == 4 for s in found)
    assert any(recipient == 'p1' and set(applied) == {'A', 'B'} and dict(returned.residuals)[path] == 1
               for path, _, recipient, _, _, applied in returned.terminals)
    assert all(len(applied) == len(set(applied)) for _, _, _, _, _, applied in returned.terminals)
    assert set(found) == set(solutions(replace(frame, packets=frame.packets[::-1])))
    # Individually each pool may spend only on damage redirected by the other.
    # They cannot BOTH do so: that would require damage with no original cause.
    chosen_a = next(v for s in found for v in s.allocations if v.pool_group == a and dict(v.vector)['left'] == 0)
    cold = Frontier.loads(choose(frame, chosen_a, 'p3').dumps())
    assert all(dict(v.vector)['right'] == 1 for v in options(cold, b, 'p2'))


def test_allocation_selection_order_does_not_impose_one_global_pool_application_order():
    frame = redirect_cycle()
    solved = solutions(frame)[0]
    left = right = frame
    for selection in solved.allocations:
        actor = next(p.controller for p in frame.pools if p.id == json.loads(selection.pool_group)[0])
        left = choose(left, selection, actor)
    for selection in reversed(solved.allocations):
        actor = next(p.controller for p in frame.pools if p.id == json.loads(selection.pool_group)[0])
        right = choose(right, selection, actor)
    assert solutions(Frontier.loads(left.dumps())) == solutions(Frontier.loads(right.dumps()))


def test_cyclic_dependency_invalidation_preserves_an_unrelated_selected_vector():
    frame = cycle()
    independent = Packet('unrelated', 'source2.old', 'p4', '', 'p4', 2, (pool('C'),))
    frame = replace(frame, packets=(*frame.packets, independent), pools=(*frame.pools, Pool('C', 'p4', 1)))
    solved = solutions(frame)[0]
    for selected in solved.allocations:
        actor = next(p.controller for p in frame.pools if p.id == json.loads(selected.pool_group)[0])
        frame = choose(frame, selected, actor)
    a = group(frame, frame.pools[0], frame.packets[0])
    c = group(frame, frame.pools[2], independent)
    refreshed = invalidate(Frontier.loads(frame.dumps()), frozenset({a}))
    assert [s.pool_group for s in refreshed.selections] == [c]
    assert solutions(refreshed)
