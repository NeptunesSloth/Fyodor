"""Stock monitoring for Shopify-style stores.

Shopify exposes lightweight product JSON at:

* ``/products/<handle>.js``   -> a single product object
* ``/products/<handle>.json`` -> ``{"product": {...}}``

Both include a ``variants`` array where each variant has ``id``, ``title`` and a
boolean ``available`` flag. We poll politely (ETag-aware) and report the first
matching available variant.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

from .config import PollConfig, ProductConfig

log = logging.getLogger("fyodor.monitor")

USER_AGENT = "Fyodor/0.1 (personal restock assistant)"


@dataclass
class VariantStock:
    variant_id: int
    title: str
    available: bool
    price: str | None = None
    inventory_quantity: int | None = None


@dataclass
class StockResult:
    product: ProductConfig
    in_stock: bool
    variant: VariantStock | None = None
    raw_description: str | None = None
    error: str | None = None


class StockMonitor:
    """Polls a single product endpoint, caching ETags between calls."""

    def __init__(self, poll: PollConfig) -> None:
        self.poll = poll
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
        self._etags: dict[str, str] = {}
        self._last_payload: dict[str, dict] = {}

    def _fetch(self, url: str) -> dict | None:
        headers = {}
        if etag := self._etags.get(url):
            headers["If-None-Match"] = etag
        try:
            resp = self._session.get(url, headers=headers, timeout=self.poll.timeout_seconds)
        except requests.RequestException as exc:
            raise _FetchError(str(exc)) from exc

        if resp.status_code == 304:
            return self._last_payload.get(url)
        if resp.status_code == 404:
            raise _FetchError("404 (wrong handle or store URL?)")
        if resp.status_code == 429:
            raise _FetchError("429 rate limited — slow down (increase poll interval)")
        resp.raise_for_status()

        if tag := resp.headers.get("ETag"):
            self._etags[url] = tag
        try:
            payload = resp.json()
        except ValueError as exc:
            raise _FetchError(f"non-JSON response: {exc}") from exc
        self._last_payload[url] = payload
        return payload

    def check(self, product: ProductConfig) -> StockResult:
        """Check one product, returning its current stock state."""
        base = f"{product.store_url}/products/{product.handle}"
        payload: dict | None = None
        last_err: str | None = None
        for suffix in (".js", ".json"):
            try:
                payload = self._fetch(base + suffix)
                break
            except _FetchError as exc:
                last_err = str(exc)
                continue

        if payload is None:
            return StockResult(product=product, in_stock=False, error=last_err or "no data")

        prod = payload.get("product", payload)
        variants = prod.get("variants") or []
        description = prod.get("body_html") or prod.get("description")

        variant = self._select_variant(product, variants)
        if variant is None:
            return StockResult(
                product=product,
                in_stock=False,
                raw_description=description,
                error="no matching variant found",
            )
        return StockResult(
            product=product,
            in_stock=variant.available,
            variant=variant,
            raw_description=description,
        )

    @staticmethod
    def _select_variant(product: ProductConfig, variants: list[dict]) -> VariantStock | None:
        def to_stock(v: dict) -> VariantStock:
            return VariantStock(
                variant_id=int(v["id"]),
                title=str(v.get("title", "")),
                available=bool(v.get("available", False)),
                price=str(v.get("price")) if v.get("price") is not None else None,
                inventory_quantity=v.get("inventory_quantity"),
            )

        stocks = [to_stock(v) for v in variants if "id" in v]
        if not stocks:
            return None

        if product.variant_id is not None:
            for s in stocks:
                if s.variant_id == product.variant_id:
                    return s
            return None
        if product.variant_title is not None:
            wanted = product.variant_title.strip().lower()
            for s in stocks:
                if s.title.strip().lower() == wanted:
                    return s
            return None

        # No explicit variant requested: prefer the first AVAILABLE one,
        # else fall back to the first so callers can still report status.
        for s in stocks:
            if s.available:
                return s
        return stocks[0]


class _FetchError(Exception):
    pass
