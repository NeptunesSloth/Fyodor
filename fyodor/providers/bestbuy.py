"""Best Buy retail provider — official Products API.

Docs: https://bestbuyapis.github.io/api-documentation/  (free API key)
Set FYODOR_BESTBUY_API_KEY. Look up by SKU (preferred) or product name search.
"""

from __future__ import annotations

import logging
import os

import httpx

from ..config import ProductConfig
from .base import NotConfigured, ProductStatus, RetailProvider

log = logging.getLogger("fyodor.providers.bestbuy")

BASE = "https://api.bestbuy.com/v1"
_FIELDS = "sku,name,salePrice,onlineAvailability,orderable,url"


class BestBuyProvider(RetailProvider):
    name = "bestbuy"
    requires = ("FYODOR_BESTBUY_API_KEY",)

    def __init__(self, client: httpx.Client | None = None, api_key: str | None = None) -> None:
        super().__init__(client)
        self.api_key = api_key or os.getenv("FYODOR_BESTBUY_API_KEY", "")

    def check(self, product: ProductConfig) -> ProductStatus:
        if not self.api_key:
            return ProductStatus(error="Best Buy: set FYODOR_BESTBUY_API_KEY (free key)")
        try:
            data = self._lookup(product)
        except NotConfigured as exc:
            return ProductStatus(error=str(exc))
        except httpx.HTTPError as exc:
            return ProductStatus(error=f"Best Buy API error: {exc}")

        products = data.get("products") or []
        if not products:
            return ProductStatus(error="Best Buy: no matching product")
        p = products[0]
        availability = str(p.get("onlineAvailability", "")).lower()
        in_stock = bool(p.get("orderable")) or availability in ("instock", "available", "true")
        return ProductStatus(
            in_stock=in_stock,
            price=p.get("salePrice"),
            variant_id=p.get("sku"),
            variant_title=p.get("name"),
            url=p.get("url"),
            raw_text=p.get("name"),
        )

    def _lookup(self, product: ProductConfig) -> dict:
        if product.sku:
            path = f"{BASE}/products(sku={product.sku})"
        elif product.model:
            path = f"{BASE}/products(modelNumber={product.model})"
        elif product.name:
            # Best Buy search syntax: products(search=term&search=term2)
            terms = "&".join(f"search={t}" for t in product.name.split())
            path = f"{BASE}/products({terms})"
        else:
            raise NotConfigured("Best Buy: product needs a sku, model, or name")
        resp = self._client.get(
            path, params={"apiKey": self.api_key, "format": "json", "show": _FIELDS, "pageSize": 1}
        )
        resp.raise_for_status()
        return resp.json()
