"""Auto-checkout via Playwright, driving a single logged-in browser profile.

What this does:
* Adds the item to the cart using a Shopify cart permalink with a clamped qty.
* Walks the standard Shopify checkout steps, relying on details already saved
  in YOUR logged-in profile (address, Shop Pay / saved card).

What this deliberately does NOT do:
* Solve CAPTCHAs, queues, or any human-verification challenge. When one appears
  it stops and hands the open browser to you.
* Rotate accounts, proxies, or fingerprints. One profile, one account.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .config import CheckoutConfig

log = logging.getLogger("fyodor.checkout")


class CheckoutStatus(str, Enum):
    PURCHASED = "purchased"
    CHALLENGE = "challenge"          # CAPTCHA / queue — handed off to human
    NEEDS_MANUAL = "needs_manual"    # reached checkout but couldn't auto-finish
    OUT_OF_STOCK = "out_of_stock"
    ERROR = "error"


@dataclass
class CheckoutResult:
    status: CheckoutStatus
    quantity: int
    message: str = ""
    checkout_url: str | None = None


# Substrings that indicate a human-verification challenge. Their presence means
# "stop and let the human take over", never "try to get around it".
_CHALLENGE_MARKERS = (
    "captcha",
    "hcaptcha",
    "recaptcha",
    "i'm not a robot",
    "verifying you are human",
    "checking your browser",
    "you are in line",
    "waiting room",
    "your place in line",
    "queue-it",
)

_OOS_MARKERS = (
    "sold out",
    "out of stock",
    "no longer available",
    "not enough items available",
)


def _import_playwright():
    try:
        from playwright.sync_api import sync_playwright  # noqa: WPS433
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Playwright is not installed. Run:\n"
            "  pip install -r requirements.txt && playwright install chromium"
        ) from exc
    return sync_playwright


class ShopifyCheckout:
    def __init__(self, config: CheckoutConfig) -> None:
        self.config = config
        Path(config.browser_profile_dir).mkdir(parents=True, exist_ok=True)

    def purchase(self, store_url: str, variant_id: int, quantity: int) -> CheckoutResult:
        if quantity < 1:
            return CheckoutResult(CheckoutStatus.ERROR, 0, "quantity clamped to 0; nothing to buy")

        sync_playwright = _import_playwright()
        timeout_ms = int(self.config.page_timeout_seconds * 1000)

        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                self.config.browser_profile_dir,
                headless=self.config.headless,
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(timeout_ms)
            try:
                return self._run(page, store_url, variant_id, quantity, timeout_ms)
            except Exception as exc:  # noqa: BLE001 - surface any driver error cleanly
                log.exception("checkout error")
                return CheckoutResult(CheckoutStatus.ERROR, quantity, str(exc))
            finally:
                # If we handed off to a human, give them a moment with the window.
                if not self.config.headless and self.config.hand_off_on_challenge:
                    pass
                context.close()

    # -- internals ---------------------------------------------------------

    def _run(self, page, store_url, variant_id, quantity, timeout_ms) -> CheckoutResult:
        store_url = store_url.rstrip("/")
        permalink = f"{store_url}/cart/{variant_id}:{quantity}"
        log.info("adding to cart via permalink: %s", permalink)
        page.goto(permalink, wait_until="domcontentloaded")

        if (challenge := self._challenge(page)) is not None:
            return challenge
        if self._out_of_stock(page):
            return CheckoutResult(CheckoutStatus.OUT_OF_STOCK, quantity, "store reported sold out")

        # Head to checkout.
        page.goto(f"{store_url}/checkout", wait_until="domcontentloaded")

        # Step through whatever the checkout throws at us, bounded by attempts.
        for _ in range(8):
            if (challenge := self._challenge(page)) is not None:
                return challenge
            if self._out_of_stock(page):
                return CheckoutResult(CheckoutStatus.OUT_OF_STOCK, quantity, "sold out at checkout")
            if self._looks_complete(page):
                return CheckoutResult(
                    CheckoutStatus.PURCHASED, quantity, "order confirmed", page.url
                )
            if not self._advance(page):
                break
            page.wait_for_load_state("domcontentloaded")

        # We got to checkout but couldn't finish automatically (e.g. a payment
        # field needs manual entry). Hand off rather than guess.
        if not self.config.headless:
            return CheckoutResult(
                CheckoutStatus.NEEDS_MANUAL,
                quantity,
                "reached checkout — finish payment in the open browser window",
                page.url,
            )
        return CheckoutResult(
            CheckoutStatus.NEEDS_MANUAL,
            quantity,
            "reached checkout but could not auto-complete (run with headless: false to finish)",
            page.url,
        )

    def _challenge(self, page) -> CheckoutResult | None:
        if not self.config.hand_off_on_challenge:
            return None
        try:
            body = (page.inner_text("body") or "").lower()
        except Exception:  # noqa: BLE001
            body = ""
        url = (page.url or "").lower()
        hit = next((m for m in _CHALLENGE_MARKERS if m in body or m in url), None)
        if hit is None:
            # Also catch CAPTCHA iframes that don't surface text in body.
            for frame in page.frames:
                fu = (frame.url or "").lower()
                if "captcha" in fu or "queue-it" in fu:
                    hit = "captcha-frame"
                    break
        if hit is None:
            return None
        log.warning("challenge detected (%s) — handing off to you", hit)
        return CheckoutResult(
            CheckoutStatus.CHALLENGE,
            0,
            f"human-verification challenge detected ('{hit}'). "
            "Fyodor stopped — complete it yourself in the browser.",
            page.url,
        )

    def _out_of_stock(self, page) -> bool:
        try:
            body = (page.inner_text("body") or "").lower()
        except Exception:  # noqa: BLE001
            return False
        return any(m in body for m in _OOS_MARKERS)

    def _looks_complete(self, page) -> bool:
        url = (page.url or "").lower()
        if "thank" in url or "/orders/" in url or "order-status" in url:
            return True
        try:
            body = (page.inner_text("body") or "").lower()
        except Exception:  # noqa: BLE001
            return False
        return "thank you" in body and "order" in body

    def _advance(self, page) -> bool:
        """Click the next standard checkout button if one is present and enabled."""
        selectors = [
            "button#continue_button",
            "button[name='button']",
            "button:has-text('Continue to shipping')",
            "button:has-text('Continue to payment')",
            "button:has-text('Pay now')",
            "button:has-text('Complete order')",
            "button:has-text('Review order')",
        ]
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if el.count() and el.is_visible() and el.is_enabled():
                    el.click()
                    log.info("clicked checkout control: %s", sel)
                    return True
            except Exception:  # noqa: BLE001
                continue
        return False
