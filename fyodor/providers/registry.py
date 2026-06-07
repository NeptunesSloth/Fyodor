"""Store capability registry + provider factories.

Single source of truth for what Fyodor can do per platform, and why. The
dashboard and CLI use this so the system is honest about coverage instead of
silently failing or scraping sites that forbid it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..config import PollConfig
from .base import (
    RetailProvider,
    SoldDataProvider,
    UnavailableRetailProvider,
    UnavailableSoldDataProvider,
)
from .bestbuy import BestBuyProvider
from .ebay import EbaySoldDataProvider
from .shopify import ShopifyProvider


class Support(str, Enum):
    OFFICIAL = "official_api"        # real connector implemented
    GATED = "needs_approval"         # official API exists but requires approval/signing
    SHOPIFY = "shopify_json"         # public product JSON
    NONE = "no_api"                  # no public API — not automated (no scraping)
    PROHIBITED = "tos_prohibited"    # automation forbidden by terms


@dataclass
class StoreCapability:
    store: str
    kind: str                        # "retail" | "resale" | "both"
    support: Support
    requires: tuple[str, ...] = ()
    note: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)


# Ordered registry covering every platform in the brief.
CAPABILITIES: dict[str, StoreCapability] = {
    "bestbuy": StoreCapability(
        "bestbuy", "retail", Support.OFFICIAL, ("FYODOR_BESTBUY_API_KEY",),
        "Best Buy Products API (free key).", aliases=("best buy", "bestbuy.com"),
    ),
    "ebay": StoreCapability(
        "ebay", "resale", Support.OFFICIAL,
        ("FYODOR_EBAY_CLIENT_ID", "FYODOR_EBAY_CLIENT_SECRET"),
        "eBay Marketplace Insights (sold data); Browse for live listings. "
        "Insights needs production approval.", aliases=("ebay.com",),
    ),
    "shopify": StoreCapability(
        "shopify", "retail", Support.SHOPIFY, (),
        "Any Shopify store via public product JSON. Covers many sneaker / "
        "collectible / LEGO-reseller / hype storefronts.",
    ),
    "walmart": StoreCapability(
        "walmart", "retail", Support.GATED, ("FYODOR_WALMART_API_KEY",),
        "Walmart Affiliate/IO API — requires approved account and request signing.",
        aliases=("walmart.com",),
    ),
    "amazon": StoreCapability(
        "amazon", "both", Support.GATED,
        ("FYODOR_AMAZON_ACCESS_KEY", "FYODOR_AMAZON_SECRET_KEY", "FYODOR_AMAZON_PARTNER_TAG"),
        "Amazon PA-API / SP-API — requires approved associate or seller account.",
        aliases=("amazon.com",),
    ),
    "target": StoreCapability(
        "target", "retail", Support.NONE, (),
        "No public API. Use Target's own deal alerts / app; not automated here.",
        aliases=("target.com",),
    ),
    "stockx": StoreCapability(
        "stockx", "resale", Support.GATED, ("FYODOR_STOCKX_API_KEY",),
        "StockX has a gated developer API (application required). No scraping.",
        aliases=("stockx.com",),
    ),
    "goat": StoreCapability(
        "goat", "resale", Support.NONE, (),
        "No public API for automation.", aliases=("goat.com",),
    ),
    "mercari": StoreCapability(
        "mercari", "resale", Support.NONE, (),
        "No public API for automation.", aliases=("mercari.com",),
    ),
    "gamestop": StoreCapability(
        "gamestop", "retail", Support.NONE, (),
        "No public API. Some storefronts are Shopify-like; verify terms first.",
        aliases=("gamestop.com",),
    ),
    "lego": StoreCapability(
        "lego", "retail", Support.NONE, (),
        "No public stock API; LEGO resale pricing is best sourced via eBay sold data.",
        aliases=("lego.com",),
    ),
    "facebook": StoreCapability(
        "facebook", "resale", Support.PROHIBITED, (),
        "Facebook Marketplace prohibits automated access. Manual only.",
        aliases=("facebook marketplace", "fb marketplace"),
    ),
    "offerup": StoreCapability(
        "offerup", "resale", Support.PROHIBITED, (),
        "OfferUp prohibits automated access. Manual only.", aliases=("offerup.com",),
    ),
}

_ALIAS_INDEX: dict[str, str] = {}
for _key, _cap in CAPABILITIES.items():
    _ALIAS_INDEX[_key] = _key
    for _a in _cap.aliases:
        _ALIAS_INDEX[_a.lower()] = _key


def resolve_store(store: str | None) -> StoreCapability | None:
    if not store:
        return None
    key = _ALIAS_INDEX.get(store.strip().lower())
    return CAPABILITIES.get(key) if key else None


def _unavailable_reason(cap: StoreCapability) -> str:
    if cap.support == Support.GATED:
        return f"{cap.store}: {cap.note} Set {', '.join(cap.requires)} once approved."
    if cap.support == Support.PROHIBITED:
        return f"{cap.store}: automation prohibited by terms — manual only."
    return f"{cap.store}: {cap.note}"


def get_retail_provider(store: str | None, poll: PollConfig | None = None) -> RetailProvider:
    """Return a stock/price provider for a store, or a clear unavailable one."""
    cap = resolve_store(store)
    if cap is None:
        # Unknown store: assume Shopify-style JSON (the config provides store_url).
        return ShopifyProvider(poll)
    if cap.support == Support.SHOPIFY:
        return ShopifyProvider(poll)
    if cap.store == "bestbuy" and cap.support == Support.OFFICIAL:
        return BestBuyProvider()
    return UnavailableRetailProvider(cap.store, _unavailable_reason(cap))


def get_sold_provider(name: str | None = "ebay") -> SoldDataProvider:
    """Return a resale sold-data provider (defaults to eBay)."""
    cap = resolve_store(name)
    if name in (None, "ebay") or (cap and cap.store == "ebay"):
        return EbaySoldDataProvider()
    if cap is None:
        return UnavailableSoldDataProvider(name or "unknown", "no sold-data provider")
    return UnavailableSoldDataProvider(cap.store, _unavailable_reason(cap))


def coverage_report() -> list[dict]:
    """Machine-readable summary for the dashboard / docs."""
    return [
        {
            "store": c.store, "kind": c.kind, "support": c.support.value,
            "requires": list(c.requires), "note": c.note,
        }
        for c in CAPABILITIES.values()
    ]
