"""Pluggable retail (stock/price) and resale (sold-data) providers."""

from .base import (
    NotConfigured,
    ProductStatus,
    ProviderError,
    RetailProvider,
    SoldDataProvider,
)
from .registry import (
    CAPABILITIES,
    StoreCapability,
    Support,
    coverage_report,
    get_retail_provider,
    get_sold_provider,
    resolve_store,
)

__all__ = [
    "ProductStatus",
    "RetailProvider",
    "SoldDataProvider",
    "ProviderError",
    "NotConfigured",
    "CAPABILITIES",
    "StoreCapability",
    "Support",
    "get_retail_provider",
    "get_sold_provider",
    "resolve_store",
    "coverage_report",
]
