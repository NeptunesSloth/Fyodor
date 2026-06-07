"""Buy recommendation engine: BUY / WATCH / SKIP with reasoning.

Combines the profitability result, the market confidence estimate, and the
configured thresholds + risk controls into a single decision plus a short,
human-readable rationale.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .market import MarketEstimate
from .profitability import CostInputs, ProfitResult, compute, min_acceptable_resale, recommended_max_buy


class Verdict(str, Enum):
    BUY = "BUY"
    WATCH = "WATCH"
    SKIP = "SKIP"


@dataclass
class Thresholds:
    min_profit: float = 15.0           # dollars net, per unit
    min_roi: float = 0.25              # fraction
    min_confidence: float = 0.5        # 0..1
    watch_confidence: float = 0.3      # below min but above this -> WATCH not SKIP
    require_data: bool = True          # SKIP if no sold data (unless manual approve)


@dataclass
class RiskControls:
    max_spend_per_product: float | None = None
    max_quantity_per_product: int | None = None
    category_blacklist: list[str] = field(default_factory=list)
    store_blacklist: list[str] = field(default_factory=list)
    require_manual_below_confidence: float = 0.5


@dataclass
class Recommendation:
    verdict: Verdict
    profit: ProfitResult
    market: MarketEstimate
    quantity: int
    min_resale: float
    max_buy: float
    reasons: list[str]
    requires_manual_approval: bool

    def summary(self) -> str:
        return " ".join(self.reasons)


def evaluate(
    *,
    inputs: CostInputs,
    market: MarketEstimate,
    thresholds: Thresholds,
    risk: RiskControls | None = None,
    category: str | None = None,
    store: str | None = None,
    limit_quantity: int | None = None,
) -> Recommendation:
    risk = risk or RiskControls()
    reasons: list[str] = []
    blockers: list[str] = []

    # --- hard risk gates -------------------------------------------------
    if category and category.lower() in {c.lower() for c in risk.category_blacklist}:
        blockers.append(f"category '{category}' is blacklisted")
    if store and store.lower() in {s.lower() for s in risk.store_blacklist}:
        blockers.append(f"store '{store}' is blacklisted")

    # --- quantity (respect store limit + configured caps) ----------------
    qty = max(inputs.quantity, 1)
    if limit_quantity is not None:
        qty = min(qty, max(limit_quantity, 0))
    if risk.max_quantity_per_product is not None:
        qty = min(qty, risk.max_quantity_per_product)
    if qty < 1:
        blockers.append("quantity clamped to 0 by limits")

    if risk.max_spend_per_product is not None:
        spend = inputs.buy_price * qty
        if spend > risk.max_spend_per_product:
            blockers.append(
                f"spend ${spend:.2f} exceeds max per product ${risk.max_spend_per_product:.2f}"
            )

    # --- data sufficiency ------------------------------------------------
    requires_manual = False
    if not market.has_data:
        if thresholds.require_data:
            return Recommendation(
                verdict=Verdict.SKIP,
                profit=compute(inputs, 0.0),
                market=market,
                quantity=qty,
                min_resale=float("inf"),
                max_buy=0.0,
                reasons=["no sold-price data available — cannot estimate resale safely"],
                requires_manual_approval=True,
            )
        requires_manual = True
        reasons.append("no sold data; manual approval required")

    resale = market.median_price
    profit = compute(inputs, resale)
    min_resale = min_acceptable_resale(inputs, min_roi=thresholds.min_roi, min_profit=thresholds.min_profit)
    max_buy = recommended_max_buy(
        resale,
        marketplace=inputs.marketplace,
        sales_tax_rate=inputs.sales_tax_rate,
        shipping_in=inputs.shipping_in,
        shipping_out=inputs.shipping_out,
        min_roi=thresholds.min_roi,
    )

    # --- evaluate economics ----------------------------------------------
    profit_ok = profit.net_profit_per_unit >= thresholds.min_profit
    roi_ok = profit.roi >= thresholds.min_roi
    conf_ok = market.confidence >= thresholds.min_confidence

    reasons.append(
        f"resale≈${resale:.2f}, net ${profit.net_profit_per_unit:.2f}/unit, "
        f"ROI {profit.roi*100:.0f}%, confidence {market.confidence:.2f} ({market.sell_through_risk} risk)"
    )

    if blockers:
        return Recommendation(
            verdict=Verdict.SKIP, profit=profit, market=market, quantity=qty,
            min_resale=min_resale, max_buy=max_buy,
            reasons=blockers + reasons, requires_manual_approval=True,
        )

    if market.confidence < risk.require_manual_below_confidence:
        requires_manual = True

    # --- verdict ---------------------------------------------------------
    if profit_ok and roi_ok and conf_ok:
        verdict = Verdict.BUY
        reasons.insert(0, "meets profit, ROI and confidence thresholds")
    elif (profit.roi >= thresholds.min_roi * 0.7 or profit_ok) and market.confidence >= thresholds.watch_confidence:
        verdict = Verdict.WATCH
        why = []
        if not profit_ok:
            why.append(f"profit ${profit.net_profit_per_unit:.2f} < ${thresholds.min_profit:.2f}")
        if not roi_ok:
            why.append(f"ROI {profit.roi*100:.0f}% < {thresholds.min_roi*100:.0f}%")
        if not conf_ok:
            why.append(f"confidence {market.confidence:.2f} < {thresholds.min_confidence:.2f}")
        reasons.insert(0, "close but below threshold: " + ", ".join(why))
    else:
        verdict = Verdict.SKIP
        reasons.insert(0, "below thresholds")

    return Recommendation(
        verdict=verdict, profit=profit, market=market, quantity=qty,
        min_resale=min_resale, max_buy=max_buy, reasons=reasons,
        requires_manual_approval=requires_manual,
    )
