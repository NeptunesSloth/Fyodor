"""Provider framework: pluggable retail (stock/price) and resale (sold-data) sources.

Two provider kinds:

* ``RetailProvider``   — given a product, report current stock + price + limit.
* ``SoldDataProvider`` — given a query, return recent *sold* records for resale
  pricing (see :mod:`fyodor.market`).

Concrete providers live alongside this module. The registry (``registry.py``)
maps a store name to the right provider, returning an explicit "unavailable"
provider — never a silent scraper — for platforms without a compliant API.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from ..config import ProductConfig
from ..market import SoldRecord

DEFAULT_TIMEOUT = 10.0
USER_AGENT = "Fyodor/0.1 (personal reselling assistant)"


@dataclass
class ProductStatus:
    """Normalised stock/price snapshot returned by every retail provider."""

    in_stock: bool = False
    price: float | None = None
    limit_per_customer: int | None = None
    available_qty: int | None = None
    variant_id: int | str | None = None
    variant_title: str | None = None
    url: str | None = None
    raw_text: str | None = None          # description/listing text for limit parsing
    error: str | None = None             # set when the source is unavailable

    @property
    def ok(self) -> bool:
        return self.error is None


class ProviderError(Exception):
    pass


class NotConfigured(ProviderError):
    """Raised/!reported when a provider needs credentials that aren't present."""


class RetailProvider:
    """Base class for stock/price providers."""

    name: str = "base"
    requires: tuple[str, ...] = ()       # env vars needed to operate

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            timeout=DEFAULT_TIMEOUT, headers={"User-Agent": USER_AGENT}
        )

    def check(self, product: ProductConfig) -> ProductStatus:  # pragma: no cover - abstract
        raise NotImplementedError


class SoldDataProvider:
    """Base class for resale sold-data providers."""

    name: str = "base"
    requires: tuple[str, ...] = ()

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            timeout=DEFAULT_TIMEOUT, headers={"User-Agent": USER_AGENT}
        )

    def recent_sold(self, query: str, *, days: int = 90, limit: int = 50) -> list[SoldRecord]:  # pragma: no cover
        raise NotImplementedError


class UnavailableRetailProvider(RetailProvider):
    """A compliant no-op for stores we can't legally/technically automate.

    It never scrapes; it returns a clear error so the system degrades gracefully
    and the dashboard/logs explain exactly what the store needs.
    """

    def __init__(self, store: str, reason: str) -> None:  # noqa: D401
        super().__init__(client=None)
        self.name = store
        self._reason = reason

    def check(self, product: ProductConfig) -> ProductStatus:
        return ProductStatus(error=self._reason)


class UnavailableSoldDataProvider(SoldDataProvider):
    def __init__(self, store: str, reason: str) -> None:
        super().__init__(client=None)
        self.name = store
        self._reason = reason

    def recent_sold(self, query: str, *, days: int = 90, limit: int = 50) -> list[SoldRecord]:
        return []
