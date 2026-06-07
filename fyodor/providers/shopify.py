"""Shopify-style retail provider (reuses the existing polite StockMonitor)."""

from __future__ import annotations

from ..config import PollConfig, ProductConfig
from ..monitor import StockMonitor
from .base import ProductStatus, RetailProvider


class ShopifyProvider(RetailProvider):
    """Covers any store exposing /products/<handle>.js|.json (many resale targets)."""

    name = "shopify"

    def __init__(self, poll: PollConfig | None = None) -> None:
        super().__init__(client=None)
        self._monitor = StockMonitor(poll or PollConfig())

    def check(self, product: ProductConfig) -> ProductStatus:
        result = self._monitor.check(product)
        if result.error and result.variant is None:
            return ProductStatus(error=result.error)
        v = result.variant
        return ProductStatus(
            in_stock=result.in_stock,
            price=float(v.price) if v and v.price else None,
            available_qty=v.inventory_quantity if v else None,
            variant_id=v.variant_id if v else None,
            variant_title=v.title if v else None,
            url=f"{product.store_url}/products/{product.handle}",
            raw_text=result.raw_description,
            error=result.error,
        )
