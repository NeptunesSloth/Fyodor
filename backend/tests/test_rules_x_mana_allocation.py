"""Exact black-on-X quotas preserve choices independently of aggregate mana spent."""
from __future__ import annotations

import pytest

from app.rules import mana as M
from app.rules import x_mana_restrictions as X


def constrained(cost, *, minimum, maximum, black, colors=('B','R'), original=None):
    return X.solver_cost(cost, {'colors':list(colors),'n':minimum,'max':maximum,
                               'generic':cost.generic if original is None else original,'black':black})


@pytest.mark.parametrize('black',[0,1,2])
def test_same_actual_payment_can_assign_different_black_counts_to_x(black):
    # Two black mana can pay fixed generic costs instead of X; this is a real choice.
    cost=M.ManaCost(generic=4,colored=('B',))
    paid=M.solve(constrained(cost,minimum=2,maximum=2,black=black),{'B':3,'R':2},[])
    assert paid.spent=={'B':3,'R':2}


def test_fixed_black_symbol_is_not_counted_as_black_spent_on_x():
    cost=M.ManaCost(generic=2,colored=('B',))
    with pytest.raises(M.ManaError):
        M.solve(constrained(cost,minimum=2,maximum=2,black=1),{'B':1,'R':2},[])
    assert M.solve(constrained(cost,minimum=2,maximum=2,black=0),{'B':1,'R':2},[]).spent=={'B':1,'R':2}


def test_nonmana_helpers_cannot_satisfy_actual_black_quota():
    cost=M.ManaCost(generic=2)
    with pytest.raises(M.ManaError):
        M.solve(constrained(cost,minimum=2,maximum=2,black=1),{'1':2},[])
    assert M.solve(constrained(cost,minimum=2,maximum=2,black=0),{'1':2},[]).spent=={'1':2}


def test_already_assigned_generic_helpers_reduce_minimum_x_requirement():
    cost=M.ManaCost(generic=2)
    paid=M.solve(constrained(cost,minimum=3,maximum=3,black=0,original=4),{'R':1,'C':1},[])
    assert paid.spent=={'R':1,'C':1}


def test_floor_generic_cannot_be_reassigned_to_fully_reduced_x():
    cost=M.ManaCost(generic=2)
    with pytest.raises(M.ManaError):
        constrained(cost,minimum=0,maximum=0,black=1)
    assert M.solve(constrained(cost,minimum=0,maximum=0,black=0),{'B':2},[]).spent=={'B':2}


def test_any_color_permission_does_not_make_blue_actual_black():
    cost=M.ManaCost(generic=2)
    with pytest.raises(M.ManaError):
        M.solve(constrained(cost,minimum=2,maximum=2,black=1,colors=M.ALL_MANA),{'U':2},[])
    assert M.solve(constrained(cost,minimum=2,maximum=2,black=0,colors=M.ALL_MANA),{'U':2},[]).spent=={'U':2}


def test_solver_only_attribution_markers_are_hidden_from_cost_display():
    cost=constrained(M.ManaCost(generic=2),minimum=2,maximum=2,black=1)
    assert X.visible(cost).text()=='{B}{R}'
