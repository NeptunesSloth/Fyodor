import math

from fyodor.fees import FeeModel
from fyodor.profitability import (
    CostInputs,
    break_even_resale,
    compute,
    min_acceptable_resale,
    recommended_max_buy,
)


def test_basic_profit_no_fees():
    fee = FeeModel("none", selling_fee_pct=0.0)
    inputs = CostInputs(buy_price=100, marketplace="x", fee_override=fee)
    r = compute(inputs, resale_price=160)
    assert r.total_cost == 100
    assert r.net_profit_per_unit == 60
    assert math.isclose(r.roi, 0.6)


def test_fees_and_shipping_reduce_profit():
    fee = FeeModel("mkt", selling_fee_pct=0.10, payment_fee_pct=0.03, payment_flat=0.30)
    inputs = CostInputs(buy_price=100, sales_tax_rate=0.10, shipping_in=5, shipping_out=10, fee_override=fee)
    r = compute(inputs, resale_price=200)
    # acquisition = 100*1.1 + 5 = 115
    assert math.isclose(r.total_cost, 115.0)
    # selling = 200*0.10 = 20; payment = 200*0.03 + 0.30 = 6.30
    assert math.isclose(r.selling_fees, 20.0)
    assert math.isclose(r.payment_fees, 6.30)
    # net_proceeds = 200 - 20 - 6.30 - 10 = 163.70 ; profit = 163.70 - 115 = 48.70
    assert math.isclose(r.net_profit_per_unit, 48.70, abs_tol=1e-6)


def test_break_even_yields_zero_profit():
    fee = FeeModel("mkt", selling_fee_pct=0.13, payment_flat=0.30)
    inputs = CostInputs(buy_price=80, shipping_out=8, fee_override=fee)
    be = break_even_resale(inputs)
    r = compute(inputs, resale_price=be)
    assert math.isclose(r.net_profit_per_unit, 0.0, abs_tol=1e-6)


def test_min_acceptable_resale_meets_constraints():
    fee = FeeModel("mkt", selling_fee_pct=0.13, payment_flat=0.30)
    inputs = CostInputs(buy_price=100, shipping_out=10, fee_override=fee)
    resale = min_acceptable_resale(inputs, min_roi=0.25, min_profit=20)
    r = compute(inputs, resale)
    assert r.roi >= 0.25 - 1e-6
    assert r.net_profit_per_unit >= 20 - 1e-6


def test_recommended_max_buy_hits_target_roi():
    fee = FeeModel("mkt", selling_fee_pct=0.10)
    max_buy = recommended_max_buy(200, fee_override=fee, min_roi=0.25, shipping_out=10)
    inputs = CostInputs(buy_price=max_buy, shipping_out=10, fee_override=fee)
    r = compute(inputs, 200)
    assert math.isclose(r.roi, 0.25, abs_tol=1e-3)


def test_quantity_scales_total_profit():
    fee = FeeModel("none", selling_fee_pct=0.0)
    inputs = CostInputs(buy_price=10, quantity=3, fee_override=fee)
    r = compute(inputs, 20)
    assert r.net_profit_total == r.net_profit_per_unit * 3
