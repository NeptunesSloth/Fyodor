"""Integer feasibility agrees with exhaustive oracle, including cyclic redirects."""
from __future__ import annotations

from dataclasses import replace

import pytest

from app.rules import prevention_frontier_prototype as frontier
from app.rules.prevention_frontier_constraints import Affine, _integer_witness, witness
from tests.test_rules_prevention_frontier_prototype import cycle, pool, redirect_cycle


@pytest.mark.parametrize('make', [cycle, redirect_cycle])
def test_every_numeric_prefix_matches_exhaustive_joint_oracle(make):
    frame = make()
    exhaustive = frontier.solutions(frame)
    assert witness(frame) in exhaustive
    for group, row, upper in frontier.rows(frame):
        for n in range(upper + 2):
            matching = [s for s in exhaustive if dict(next(a.vector for a in s.allocations if a.pool_group == group))[row] == n]
            result = witness(frame, ((group, row, n),))
            assert (result is not None) == bool(matching), (group, row, n)
            assert result is None or result in matching
    for solution in exhaustive:
        selected = replace(frame, selections=solution.allocations)
        assert witness(frontier.Frontier.loads(selected.dumps())) == solution


def test_billion_damage_and_budget_do_not_require_vector_enumeration():
    frame = cycle()
    frame = replace(frame, packets=tuple(replace(p, amount=10**9) for p in frame.packets),
                    pools=tuple(replace(p, remaining=4 * 10**8) for p in frame.pools))
    a = frontier.group(frame, frame.pools[0], frame.packets[0])
    b = frontier.group(frame, frame.pools[1], frame.packets[0])
    result = witness(frame, ((a, 'left', 10**8), (a, 'right', 3 * 10**8), (b, 'left', 3 * 10**8)))
    assert result is not None
    assert result.residuals == (('left', 6 * 10**8), ('right', 6 * 10**8))


def test_protection_furnace_unpreventable_and_insufficient_budget_match_oracle():
    frame = frontier.Frontier('batch', (
        frontier.Packet('left', 'old', 'p1', '', 'p1', 2, (frontier.Operation('furnace', 'multiply', factor=2), pool('A'))),
        frontier.Packet('right', 'old', 'p2', '', 'p2', 2, (pool('A'),), unpreventable=True),
        frontier.Packet('protected', 'old', 'p3', '', 'p3', 2, (frontier.Operation('protection', 'protection'), pool('A'))),
    ), (frontier.Pool('A', 'p1', 7),))
    assert witness(frame) == frontier.solutions(frame)[0]


def test_integer_constraints_reject_fractional_only_solution():
    key = ('pool', 'row')
    twice_minus_one = Affine(-1, ((key, 2),))
    # 2x=1 has a rational solution but no legal integer damage allocation.
    assert _integer_witness({key: (0, 10**9)}, (twice_minus_one, twice_minus_one.scale(-1))) is None


def test_inconsistent_saved_vectors_or_invalid_prefix_are_rejected():
    frame = cycle()
    a = frontier.group(frame, frame.pools[0], frame.packets[0])
    frame = replace(frame, selections=(frontier.Selection(a, (('left', 1), ('right', 2))),))
    assert witness(frame, ((a, 'left', 2),)) is None
    assert witness(frame, (('not-a-pool', 'left', 1),)) is None
    assert witness(frame, ((a, 'left', -1),)) is None
