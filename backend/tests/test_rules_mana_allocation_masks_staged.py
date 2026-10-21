"""Opt-in isolated allocation prototype; no production parser or solver adapters."""
import pytest
from pydantic import TypeAdapter

from app.rules import mana as M
from app.rules import mana_allocation_masks as A


def source(output='WUBRG', *, masks=(False,), abilities=(7,), snow=False):
    return A.MaskedSource(M.Source('producer', tuple(tuple(x) for x in output.split(',')),
                                  abilities=abilities, snow=snow), masks)


@pytest.mark.parametrize('iterative', [False, True])
def test_restricted_units_pay_symbols_but_never_generic(iterative):
    s = source()
    assert A.solve(M.parse_cost('{W}{U}{B}{R}{G}'), {}, [s], iterative=iterative).payment.spent == dict.fromkeys('WUBRG', 1)
    for text in ('{5}', '{C}', '{2}'):
        with pytest.raises(M.ManaError):
            A.solve(M.parse_cost(text), {}, [s], iterative=iterative)
    assert A.solve(M.parse_cost('{2/W}'), {}, [s], iterative=iterative).payment.spent == {'W': 1}


@pytest.mark.parametrize('iterative', [False, True])
def test_exact_option_identity_and_actual_settlement(iterative):
    dual = source('R,R', masks=(False, True), abilities=(7, 9))
    assert A.solve(M.parse_cost('{1}'), {}, [dual], iterative=iterative).payment.used == [('producer', 9)]
    assert A.solve(M.parse_cost('{R}'), {}, [dual], iterative=iterative).payment.used == [('producer', 7)]
    result = A.solve(M.parse_cost('{1}{G}'), {'W': 1}, [source()], iterative=iterative)
    slots = [A.Slot(A.UnitClass(c, False), 'producer') for c in 'WUBRG']
    paid = A.settle(result.allocation, slots)
    assert [s.unit.sym for s in paid.spent] == ['G']
    assert paid.plain_delta == {'W': -1}
    assert {s.unit.sym for s in paid.produced_left} == set('WUBR')
    receipt = TypeAdapter(list[A.SpentClass])
    assert receipt.validate_json(receipt.dump_json(result.allocation)) == result.allocation


@pytest.mark.parametrize('iterative', [False, True])
@pytest.mark.parametrize('mode', ['type', 'color'])
def test_as_though_preserves_colored_origin(iterative, mode):
    cost = M.parse_cost('{1}{W}')
    result = A.solve(cost, {'C': 1}, [source('R')], mode=mode, iterative=iterative)
    assert result.payment.spent == {'C': 1, 'R': 1}
    with pytest.raises(M.ManaError):
        A.solve(cost, {}, [source('RR')], mode=mode, iterative=iterative)


@pytest.mark.parametrize('iterative', [False, True])
@pytest.mark.parametrize('alternatives', [('B', '@X'), ('R',)])
def test_assigned_x_and_filter_inputs_remain_generic(iterative, alternatives):
    cost = M.parse_cost('{1}')
    plan = A.constrain_generic(A.requirements(cost), (alternatives,))
    with pytest.raises(M.ManaError):
        A.solve(cost, {}, [source(alternatives[0])], plan=plan, iterative=iterative)
    assert A.solve(cost, {}, [source(alternatives[0], masks=(True,))], plan=plan,
                   iterative=iterative).payment.spent == {alternatives[0]: 1}


@pytest.mark.parametrize('iterative', [False, True])
def test_snow_phyrexian_and_abstruse_keep_actual_unit_classes(iterative):
    snow = source('UU', snow=True)
    result = A.solve(M.ManaCost(colored=('S', 'S')), {}, [snow], iterative=iterative)
    assert result.payment.spent == {'U': 2}
    assert result.allocation == [A.SpentClass(A.UnitClass('U', False, True), 2)]
    with pytest.raises(M.ManaError):
        A.solve(M.ManaCost(colored=('S',)), {}, [source('U', snow=True, abilities=(-1,))], iterative=iterative)
    assert A.solve(M.parse_cost('{W/P}{U/P}'), {}, [], life=4, iterative=iterative).payment.life == 4
    assert A.solve(M.parse_cost('{W/P}'), {}, [source('W')], iterative=iterative).payment.life == 0
    result = A.solve(M.parse_cost('{2}{W}{C}'), {'R': 2}, [source('CC')],
                     mode='colorless_color', iterative=iterative)
    assert result.payment.spent == {'R': 2, 'C': 2}


def test_large_cost_and_typed_settlement_cannot_fabricate_units():
    cost = M.ManaCost(colored=('W',) * 260)
    assert A.solve(cost, {'W': 260}, []).payment.spent == {'W': 260}
    with pytest.raises(M.ManaError):
        A.settle([A.SpentClass(A.UnitClass('W', False), 1)],
                 [A.Slot(A.UnitClass('W'), 'wrong', unit_id=1)])


def test_color_as_though_does_not_rewrite_numeric_hybrid():
    with pytest.raises(M.ManaError):
        A.solve(M.parse_cost('{2/W}'), {}, [source('R')], mode='color')
    assert A.solve(M.parse_cost('{2/W}'), {}, [source('R')], mode='type').payment.spent == {'R': 1}


def test_native_solver_dispatch_preserves_matching_origin_and_exact_receipt():
    masked = M.Source('producer', (('W', 'U', 'B', 'R', 'G'),), abilities=(7,), generic_allowed=(False,))
    payment = M.solve(M.parse_cost('{1}{G}'), {'W': 1}, [masked])
    assert payment.allocation == [A.SpentClass(A.UnitClass('W'), 1), A.SpentClass(A.UnitClass('G', False), 1)]
    cost = M.spend_as(M.parse_cost('{1}{W}'), 'type')
    with pytest.raises(M.ManaError):
        M.solve(cost, {}, [masked])
    assert M.solve(cost, {'C': 1}, [masked]).spent == {'C': 1, 'W': 1}
    assert M.solve(M.parse_cost('{1}'), {'W': 1}, []).allocation is None


def test_as_though_mana_does_not_recolor_nonmana_helpers():
    cost = M.spend_as(M.parse_cost('{W}'), 'color')
    blue_convoke = M.Source('helper', (('U',),), abilities=(-1,))
    masked = M.Source('irrelevant', (('R',),), generic_allowed=(False,))
    # Restricted R is legitimate mana for the white requirement under as-though;
    # the blue convoke contribution itself cannot be recolored by that permission.
    result = M.solve(cost, {}, [blue_convoke, masked])
    assert result.used == [] and result.tapped == ['irrelevant']


def test_native_filter_generic_input_retains_origin_through_assigned_payment():
    from app.rules import casting

    restricted = M.Source('producer', (('W',),), generic_allowed=(False,))
    filter_source = M.Source('filter', (('U',),), abilities=(2,), activation=M.parse_cost('{1}'))
    with pytest.raises(M.ManaError):
        casting._solve_with_filters(M.parse_cost('{U}'), {}, [restricted], [filter_source], 0)
    result = casting._solve_with_filters(M.parse_cost('{U}'), {'C': 1}, [restricted], [filter_source], 0)
    assigned = result.filters[0][3]
    assert assigned.allocation is not None
    with pytest.raises(M.ManaError):
        M.solve(assigned, {}, [restricted])
    assert M.solve(assigned, {'C': 1}, [restricted]).spent == {'C': 1}


def test_native_helper_removal_keeps_as_though_origins_and_announced_phyrexian():
    from app.rules import casting, payment

    cost = M.spend_as(M.parse_cost('{1}{W}'), 'color')
    assert payment.assign(cost, [payment.Helper('convoke', 'blue', frozenset({'U'}))]) == ['1']
    remaining = payment.remaining(cost, ['1'])
    restricted = M.Source('producer', (('U',),), generic_allowed=(False,))
    assert M.solve(remaining, {}, [restricted]).spent == {'U': 1}
    assert payment.assign(cost, [payment.Helper('convoke', 'blue1', frozenset({'U'})),
                                 payment.Helper('convoke', 'blue2', frozenset({'U'}))]) is None
    phy = casting.split_phyrexian(M.spend_as(M.parse_cost('{W/P}{U/P}'), 'type'), [M.ANY_PHYREXIAN])
    assert M.solve(phy, {}, [restricted]).spent == {'U': 1}


@pytest.mark.parametrize('text,pool,outputs,life', [
    ('{2}{W}', {'W': 1}, ['CC'], 0),
    ('{U/R}{G}', {}, ['U', 'G'], 0),
    ('{2/W}{B}', {}, ['CC', 'B'], 0),
    ('{W/P}{U/P}', {}, [], 4),
    ('{1}{R}{R}', {'C': 1}, ['RR'], 0),
    ('{C}{G}', {}, ['C', 'G'], 0),
    ('{3}', {}, ['W', 'UU'], 0),
    ('{B}', {}, ['R'], 0),
])
def test_unmasked_allocation_matches_native_solver(text, pool, outputs, life):
    cost = M.parse_cost(text)
    sources = [M.Source(str(i), (tuple(output),), abilities=(i,)) for i, output in enumerate(outputs)]
    try:
        native = M.solve(cost, pool, sources, life=life)
    except M.ManaError:
        with pytest.raises(M.ManaError):
            A.solve(cost, pool, [A.MaskedSource(s) for s in sources], life=life)
    else:
        for iterative in (False, True):
            staged = A.solve(cost, pool, [A.MaskedSource(s) for s in sources], life=life, iterative=iterative).payment
            assert (staged.spent, staged.produced, staged.used, staged.life) == (
                native.spent, native.produced, native.used, native.life)
