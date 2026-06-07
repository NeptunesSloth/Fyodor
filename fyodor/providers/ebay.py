"""eBay resale provider — official APIs for sold-price data.

* OAuth2 client-credentials for an application token.
* Marketplace Insights API (`item_sales/search`) for recent SOLD prices — this
  is the resale-pricing signal Fyodor prefers. It requires production access
  approval from eBay; until then ``recent_sold`` returns [] with a clear log.
* Browse API (`item_summary/search`) is also available for live listing prices
  as a fallback.

Set FYODOR_EBAY_CLIENT_ID and FYODOR_EBAY_CLIENT_SECRET (free developer keys).
"""

from __future__ import annotations

import base64
import logging
import os
import time
from datetime import datetime, timezone

import httpx

from ..market import SoldRecord
from .base import SoldDataProvider

log = logging.getLogger("fyodor.providers.ebay")

OAUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
INSIGHTS_URL = "https://api.ebay.com/buy/marketplace_insights/v1_beta/item_sales/search"
BROWSE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
SCOPE = "https://api.ebay.com/oauth/api_scope"


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


class EbaySoldDataProvider(SoldDataProvider):
    name = "ebay"
    requires = ("FYODOR_EBAY_CLIENT_ID", "FYODOR_EBAY_CLIENT_SECRET")

    def __init__(
        self,
        client: httpx.Client | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        marketplace: str = "EBAY_US",
    ) -> None:
        super().__init__(client)
        self.client_id = client_id or os.getenv("FYODOR_EBAY_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("FYODOR_EBAY_CLIENT_SECRET", "")
        self.marketplace = marketplace
        self._token: str | None = None
        self._token_expiry: float = 0.0

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _auth_header(self) -> dict[str, str]:
        if self._token and time.time() < self._token_expiry - 60:
            return {"Authorization": f"Bearer {self._token}"}
        creds = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        resp = self._client.post(
            OAUTH_URL,
            headers={"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials", "scope": SCOPE},
        )
        resp.raise_for_status()
        body = resp.json()
        self._token = body["access_token"]
        self._token_expiry = time.time() + int(body.get("expires_in", 7200))
        return {"Authorization": f"Bearer {self._token}"}

    def recent_sold(self, query: str, *, days: int = 90, limit: int = 50) -> list[SoldRecord]:
        if not self.configured:
            log.info("eBay sold-data not configured; set FYODOR_EBAY_CLIENT_ID/SECRET")
            return []
        try:
            headers = {**self._auth_header(), "X-EBAY-C-MARKETPLACE-ID": self.marketplace}
            resp = self._client.get(
                INSIGHTS_URL, headers=headers, params={"q": query, "limit": min(limit, 100)}
            )
            if resp.status_code == 403:
                log.warning("eBay Marketplace Insights needs production access approval (403)")
                return []
            resp.raise_for_status()
            return self._parse_sales(resp.json())
        except httpx.HTTPError as exc:
            log.warning("eBay sold-data request failed: %s", exc)
            return []

    @staticmethod
    def _parse_sales(payload: dict) -> list[SoldRecord]:
        records: list[SoldRecord] = []
        for sale in payload.get("itemSales", []) or []:
            price_obj = sale.get("lastSoldPrice") or sale.get("price") or {}
            try:
                price = float(price_obj.get("value"))
            except (TypeError, ValueError):
                continue
            records.append(
                SoldRecord(
                    price=price,
                    sold_at=_parse_dt(sale.get("lastSoldDate")),
                    marketplace="ebay",
                    condition=str(sale.get("condition", "unknown")),
                )
            )
        return records
