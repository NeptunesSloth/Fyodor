"""Marketplace fee models.

These are approximate, configurable defaults for *selling* fees on common
resale marketplaces. Real fees vary by category, seller tier, and promotions —
override per-product or per-config where it matters. Sources are each
marketplace's published fee schedule (subject to change).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeeModel:
    """A marketplace's selling-fee structure.

    * ``selling_fee_pct``   — final-value / commission fee as a fraction of sale price.
    * ``payment_fee_pct``   — payment processing percentage.
    * ``payment_flat``      — flat per-transaction payment fee.
    * ``flat_fee``          — any fixed marketplace fee per sale.
    """

    name: str
    selling_fee_pct: float
    payment_fee_pct: float = 0.0
    payment_flat: float = 0.0
    flat_fee: float = 0.0

    def total_variable_pct(self) -> float:
        return self.selling_fee_pct + self.payment_fee_pct


# Approximate published defaults (as of 2025). Adjust in config as needed.
DEFAULT_FEES: dict[str, FeeModel] = {
    "ebay": FeeModel("ebay", selling_fee_pct=0.1325, payment_flat=0.30),
    "amazon": FeeModel("amazon", selling_fee_pct=0.15),
    "stockx": FeeModel("stockx", selling_fee_pct=0.09, payment_fee_pct=0.03),
    "goat": FeeModel("goat", selling_fee_pct=0.095, payment_fee_pct=0.029, payment_flat=0.30),
    "mercari": FeeModel("mercari", selling_fee_pct=0.10, payment_fee_pct=0.029, payment_flat=0.50),
    "facebook": FeeModel("facebook", selling_fee_pct=0.0),   # local pickup
    "offerup": FeeModel("offerup", selling_fee_pct=0.0),     # local pickup
    "local": FeeModel("local", selling_fee_pct=0.0),
}

GENERIC_PAYMENT = FeeModel("generic", selling_fee_pct=0.0, payment_fee_pct=0.029, payment_flat=0.30)


def get_fee_model(marketplace: str | None) -> FeeModel:
    if not marketplace:
        return DEFAULT_FEES["ebay"]
    return DEFAULT_FEES.get(marketplace.strip().lower(), DEFAULT_FEES["ebay"])
