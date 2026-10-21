"""Large costs preserve normal solver order and backtracking without recursive depth limits."""
from __future__ import annotations

import pytest

from app.rules import mana as M


@pytest.mark.parametrize('n',[255,256,1000])
def test_large_single_color_payment_matches_exact_requirement_count(n):
    cost=M.ManaCost(generic=1,colored=('B',)*n)
    payment=M.solve(cost,{'B':n,'R':1},[])
    assert payment.spent=={'B':n,'R':1}


def test_large_hybrid_payment_backtracks_to_leave_black_for_later_slot():
    cost=M.ManaCost(hybrid=(('B','R'),)*299+(('B','U'),))
    payment=M.solve(cost,{'B':299,'R':1},[])
    assert payment.spent=={'B':299,'R':1}


def test_large_two_generic_hybrid_uses_generic_alternative():
    cost=M.ManaCost(hybrid=(('2','B'),)*300)
    assert M.solve(cost,{'C':600},[]).spent=={'C':600}


def test_large_impossible_color_payment_returns_mana_error():
    with pytest.raises(M.ManaError):
        M.solve(M.ManaCost(colored=('B',)*1000),{'R':1000},[])
