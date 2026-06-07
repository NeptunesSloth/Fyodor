"""Market price comparison and opportunity confidence scoring.

We deliberately base resale estimates on *sold / completed* data points rather
than asking prices, which are noisy and often aspirational. Sold data comes from
pluggable providers (see :class:`SoldDataProvider`). A manual provider is
included; real connectors (eBay Marketplace Insights, StockX, etc.) require API
keys and are added as separate provider implementations.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol


@dataclass
class SoldRecord:
    price: float
    sold_at: datetime
    marketplace: str = "unknown"
    condition: str = "new"


@dataclass
class MarketEstimate:
    sample_size: int
    median_price: float
    mean_price: float
    low_price: float
    high_price: float
    coef_variation: float          # stddev / mean; lower == tighter, more reliable
    recent_velocity_per_week: float
    confidence: float              # 0..1
    sell_through_risk: str         # "low" | "medium" | "high"
    time_to_sell_days: float | None
    marketplaces: list[str] = field(default_factory=list)

    @property
    def has_data(self) -> bool:
        return self.sample_size > 0


class SoldDataProvider(Protocol):
    def recent_sold(self, *, query: str, days: int = 90) -> list[SoldRecord]:  # pragma: no cover
        ...


class ManualSoldDataProvider:
    """Sold data supplied directly (e.g. from config, CSV, or a JSON import)."""

    def __init__(self, records: dict[str, list[SoldRecord]] | None = None) -> None:
        self._records = records or {}

    def add(self, query: str, records: list[SoldRecord]) -> None:
        self._records.setdefault(query, []).extend(records)

    def recent_sold(self, *, query: str, days: int = 90) -> list[SoldRecord]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        return [r for r in self._records.get(query, []) if r.sold_at >= cutoff]


def estimate_from_prices(prices: list[float], *, days_span: int = 30) -> MarketEstimate:
    """Convenience: build an estimate from a bare list of recent sold prices.

    Spreads the points across ``days_span`` so velocity/confidence are sane.
    """
    prices = [p for p in prices if p > 0]
    if not prices:
        return estimate_market([])
    now = datetime.now(timezone.utc)
    step = max(days_span / max(len(prices), 1), 1)
    records = [
        SoldRecord(price=p, sold_at=now - timedelta(days=step * i)) for i, p in enumerate(prices)
    ]
    return estimate_market(records)


def _trim_outliers(prices: list[float]) -> list[float]:
    """Drop the most extreme listings using a simple IQR filter."""
    if len(prices) < 4:
        return sorted(prices)
    s = sorted(prices)
    q1 = s[len(s) // 4]
    q3 = s[(len(s) * 3) // 4]
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    trimmed = [p for p in s if lo <= p <= hi]
    return trimmed or s


def estimate_market(records: list[SoldRecord]) -> MarketEstimate:
    """Build a resale estimate + confidence score from sold records."""
    if not records:
        return MarketEstimate(
            sample_size=0, median_price=0.0, mean_price=0.0, low_price=0.0,
            high_price=0.0, coef_variation=1.0, recent_velocity_per_week=0.0,
            confidence=0.0, sell_through_risk="high", time_to_sell_days=None,
        )

    prices = _trim_outliers([r.price for r in records if r.price > 0])
    median = statistics.median(prices)
    mean = statistics.fmean(prices)
    stdev = statistics.pstdev(prices) if len(prices) > 1 else 0.0
    cov = (stdev / mean) if mean > 0 else 1.0

    now = datetime.now(timezone.utc)
    span_days = max((now - min(r.sold_at for r in records)).days, 1)
    velocity_per_week = len(records) / (span_days / 7.0)
    tts = (7.0 / velocity_per_week) if velocity_per_week > 0 else None

    # Confidence: more samples + tighter spread + recent sales == higher.
    sample_factor = min(len(records) / 15.0, 1.0)          # saturates at ~15 sales
    spread_factor = max(0.0, 1.0 - min(cov, 1.0))           # 1 when CoV≈0
    velocity_factor = min(velocity_per_week / 3.0, 1.0)     # saturates at 3/week
    confidence = round(0.45 * sample_factor + 0.35 * spread_factor + 0.20 * velocity_factor, 3)

    if confidence >= 0.66 and velocity_per_week >= 1:
        risk = "low"
    elif confidence >= 0.4:
        risk = "medium"
    else:
        risk = "high"

    return MarketEstimate(
        sample_size=len(records),
        median_price=round(median, 2),
        mean_price=round(mean, 2),
        low_price=round(min(prices), 2),
        high_price=round(max(prices), 2),
        coef_variation=round(cov, 3),
        recent_velocity_per_week=round(velocity_per_week, 2),
        confidence=confidence,
        sell_through_risk=risk,
        time_to_sell_days=round(tts, 1) if tts else None,
        marketplaces=sorted({r.marketplace for r in records}),
    )
