"""Profitability engine.

Given a buy price and an expected resale price (plus tax/shipping/fees), compute
net profit, ROI, break-even resale, the minimum acceptable resale price, and the
recommended maximum buy price for a target ROI.

All money is handled as floats in whole currency units (e.g. dollars). Keep it
simple; resale margins are noisy enough that sub-cent precision is theatre.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .fees import FeeModel, get_fee_model


@dataclass
class CostInputs:
    buy_price: float
    quantity: int = 1
    sales_tax_rate: float = 0.0      # fraction, e.g. 0.0825
    shipping_in: float = 0.0          # cost to acquire the item (per unit)
    shipping_out: float = 0.0         # cost to ship to buyer (per unit)
    marketplace: str = "ebay"
    fee_override: FeeModel | None = None


@dataclass
class ProfitResult:
    buy_price: float
    quantity: int
    resale_price: float
    sales_tax: float
    shipping_in: float
    shipping_out: float
    selling_fees: float
    payment_fees: float
    total_cost: float          # what you pay to acquire (per unit)
    net_proceeds: float        # what you net from the sale after fees/ship (per unit)
    net_profit_per_unit: float
    net_profit_total: float
    roi: float                 # fraction; 0.25 == 25%
    margin: float              # net profit / resale price
    break_even_resale: float
    marketplace: str

    def as_dict(self) -> dict:
        return asdict(self)


def _fee_model(inputs: CostInputs) -> FeeModel:
    return inputs.fee_override or get_fee_model(inputs.marketplace)


def acquisition_cost(inputs: CostInputs) -> float:
    """Per-unit cost to acquire the item (buy + tax + inbound shipping)."""
    return inputs.buy_price * (1 + inputs.sales_tax_rate) + inputs.shipping_in


def _selling_costs(resale_price: float, fee: FeeModel) -> tuple[float, float]:
    selling = resale_price * fee.selling_fee_pct + fee.flat_fee
    payment = resale_price * fee.payment_fee_pct + fee.payment_flat
    return selling, payment


def break_even_resale(inputs: CostInputs) -> float:
    """Resale price at which net profit is exactly zero (per unit).

    total_cost = resale*(1 - selling_pct - payment_pct) - flat_fees - shipping_out
    => resale = (total_cost + flat_fees + shipping_out) / (1 - variable_pct)
    """
    fee = _fee_model(inputs)
    total_cost = acquisition_cost(inputs)
    variable = fee.total_variable_pct()
    flat = fee.flat_fee + fee.payment_flat
    denom = 1.0 - variable
    if denom <= 0:
        return float("inf")
    return (total_cost + flat + inputs.shipping_out) / denom


def compute(inputs: CostInputs, resale_price: float) -> ProfitResult:
    fee = _fee_model(inputs)
    total_cost = acquisition_cost(inputs)
    selling, payment = _selling_costs(resale_price, fee)
    net_proceeds = resale_price - selling - payment - inputs.shipping_out
    net_per_unit = net_proceeds - total_cost
    qty = max(inputs.quantity, 1)

    roi = net_per_unit / total_cost if total_cost > 0 else 0.0
    margin = net_per_unit / resale_price if resale_price > 0 else 0.0

    return ProfitResult(
        buy_price=inputs.buy_price,
        quantity=qty,
        resale_price=resale_price,
        sales_tax=inputs.buy_price * inputs.sales_tax_rate,
        shipping_in=inputs.shipping_in,
        shipping_out=inputs.shipping_out,
        selling_fees=selling,
        payment_fees=payment,
        total_cost=total_cost,
        net_proceeds=net_proceeds,
        net_profit_per_unit=net_per_unit,
        net_profit_total=net_per_unit * qty,
        roi=roi,
        margin=margin,
        break_even_resale=break_even_resale(inputs),
        marketplace=fee.name,
    )


def min_acceptable_resale(inputs: CostInputs, *, min_roi: float = 0.0, min_profit: float = 0.0) -> float:
    """Lowest resale price that satisfies BOTH a min ROI and a min $ profit.

    Solve resale for each constraint, take the higher (more demanding) one.
    """
    fee = _fee_model(inputs)
    total_cost = acquisition_cost(inputs)
    variable = fee.total_variable_pct()
    flat = fee.flat_fee + fee.payment_flat
    denom = 1.0 - variable
    if denom <= 0:
        return float("inf")

    # net = resale*denom - flat - shipping_out - total_cost
    # ROI constraint: net >= min_roi * total_cost
    resale_for_roi = (total_cost * (1 + min_roi) + flat + inputs.shipping_out) / denom
    # Profit constraint: net >= min_profit
    resale_for_profit = (total_cost + min_profit + flat + inputs.shipping_out) / denom
    return max(resale_for_roi, resale_for_profit)


def recommended_max_buy(
    resale_price: float,
    *,
    marketplace: str = "ebay",
    sales_tax_rate: float = 0.0,
    shipping_in: float = 0.0,
    shipping_out: float = 0.0,
    min_roi: float = 0.25,
    fee_override: FeeModel | None = None,
) -> float:
    """Highest buy price that still clears ``min_roi`` at the given resale price.

    net_proceeds is fixed by resale; net = net_proceeds - acq(buy).
    Require net >= min_roi * acq(buy)  =>  net_proceeds >= acq(buy) * (1 + min_roi)
    acq(buy) = buy*(1+tax) + shipping_in
    => buy <= (net_proceeds/(1+min_roi) - shipping_in) / (1+tax)
    """
    fee = fee_override or get_fee_model(marketplace)
    selling, payment = _selling_costs(resale_price, fee)
    net_proceeds = resale_price - selling - payment - shipping_out
    allowed_acq = net_proceeds / (1.0 + min_roi)
    buy = (allowed_acq - shipping_in) / (1.0 + sales_tax_rate)
    return max(buy, 0.0)
