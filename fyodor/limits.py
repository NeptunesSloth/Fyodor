"""Purchase-limit enforcement.

This is the heart of the "if the limit is 2, buy 2 — not more" rule. Every
quantity that flows toward checkout passes through :func:`clamp_quantity`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class QuantityDecision:
    quantity: int
    reason: str

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.quantity} ({self.reason})"


# Phrases stores commonly use to advertise a per-customer cap. We read these to
# *respect* the cap, never to exceed it.
_LIMIT_PATTERNS = [
    re.compile(r"limit\s*(?:of\s*)?(\d+)\s*per\s*(?:customer|person|order|household)", re.I),
    re.compile(r"max(?:imum)?\s*(\d+)\s*per\s*(?:customer|person|order|household)", re.I),
    re.compile(r"(\d+)\s*per\s*(?:customer|person|household)\s*limit", re.I),
]


def detect_limit_from_text(text: str | None) -> int | None:
    """Best-effort parse of a per-customer limit from free-form store text.

    Returns the smallest advertised limit found, or ``None`` if none is detected.
    """
    if not text:
        return None
    found: list[int] = []
    for pattern in _LIMIT_PATTERNS:
        for match in pattern.finditer(text):
            try:
                value = int(match.group(1))
            except (TypeError, ValueError):
                continue
            if value > 0:
                found.append(value)
    return min(found) if found else None


def clamp_quantity(
    desired: int,
    *,
    detected_limit: int | None = None,
    configured_cap: int | None = None,
    variant_available_qty: int | None = None,
) -> QuantityDecision:
    """Return the quantity to actually request, never exceeding any known cap.

    Priority of caps (the most restrictive always wins):

    * ``detected_limit``        — a per-customer limit parsed from the store.
    * ``configured_cap``        — ``max_per_customer`` from config.
    * ``variant_available_qty`` — stock the store reports as available.
    * ``desired``               — what the user asked for.
    """
    caps: list[tuple[int, str]] = [(max(desired, 0), "desired")]
    if detected_limit is not None:
        caps.append((detected_limit, "store per-customer limit"))
    if configured_cap is not None:
        caps.append((configured_cap, "configured cap"))
    if variant_available_qty is not None:
        caps.append((variant_available_qty, "available stock"))

    quantity, reason = min(caps, key=lambda c: c[0])
    quantity = max(quantity, 0)
    return QuantityDecision(quantity=quantity, reason=reason)
