"""Command-line entry point: watch loop, web server, db setup."""

from __future__ import annotations

import argparse
import logging
import random
import signal
import sys
import time
from urllib.parse import urlparse

from . import repository as repo
from .checkout import CheckoutStatus, ShopifyCheckout
from .config import Config, ConfigError, ProductConfig, load_config
from .db import init_db
from .limits import clamp_quantity, detect_limit_from_text
from .market import MarketEstimate, estimate_from_prices
from .monitor import StockMonitor, StockResult
from .notifier import Notifier
from .profitability import CostInputs
from .recommend import RiskControls, Thresholds, Verdict, evaluate

log = logging.getLogger("fyodor")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _store_label(product: ProductConfig) -> str:
    host = urlparse(product.store_url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


class Fyodor:
    def __init__(self, config: Config, *, dry_run: bool = False) -> None:
        self.config = config
        self.dry_run = dry_run or config.modes.dry_run
        self.alert_only = config.modes.alert_only
        self.paper = config.modes.paper
        self.monitor = StockMonitor(config.poll)
        self.notifier = Notifier(config.notify)
        checkout_live = config.checkout.enabled and not (self.dry_run or self.alert_only or self.paper)
        self.checkout = ShopifyCheckout(config.checkout) if checkout_live else None
        self.thresholds = Thresholds(
            min_profit=config.thresholds.min_profit,
            min_roi=config.thresholds.min_roi,
            min_confidence=config.thresholds.min_confidence,
            watch_confidence=config.thresholds.watch_confidence,
            require_data=config.thresholds.require_data,
        )
        self.risk = RiskControls(
            max_spend_per_product=config.risk.max_spend_per_product,
            max_quantity_per_product=config.risk.max_quantity_per_product,
            category_blacklist=config.risk.category_blacklist,
            store_blacklist=config.risk.store_blacklist,
            require_manual_below_confidence=config.risk.require_manual_below_confidence,
        )
        self.purchases = 0
        self._done: set[str] = set()
        self._item_ids: dict[str, int] = {}
        self._stop = False

    def request_stop(self, *_a) -> None:
        self._stop = True
        log.info("stop requested — finishing current cycle")

    # -- setup ------------------------------------------------------------

    def _sync_watchlist(self) -> None:
        """Ensure each configured product has a DB watch item for tracking."""
        init_db()
        for p in self.config.products:
            store = _store_label(p)
            item_id = repo.get_or_create_watch_item(
                name=p.name, store=store, url=f"{p.store_url}/products/{p.handle}",
                category=p.category, desired_quantity=p.desired_quantity,
                max_per_customer=p.max_per_customer, max_buy_price=p.max_buy_price,
                resale_marketplace=p.resale_marketplace, sales_tax_rate=p.sales_tax_rate,
                shipping_in=p.shipping_in, shipping_out=p.shipping_out,
                manual_resale_estimate=p.manual_resale_estimate,
            )
            self._item_ids[self._key(p)] = item_id

    def _key(self, product: ProductConfig) -> str:
        return f"{product.store_url}|{product.handle}|{product.variant_id or product.variant_title or '*'}"

    # -- main loop --------------------------------------------------------

    def run(self, *, once: bool = False) -> int:
        if not self.config.products:
            log.warning("no products configured under 'products:' — nothing to watch")
            return 0
        self._sync_watchlist()
        mode = "alert-only" if self.alert_only else "paper" if self.paper else "dry-run" if self.dry_run else "live"
        log.info(
            "watching %d product(s); interval ~%.1fs; mode=%s; checkout=%s",
            len(self.config.products), self.config.poll.effective_interval(), mode,
            "on" if self.checkout else "off",
        )
        cap = self.config.checkout.max_purchases_per_run

        while not self._stop:
            for product in self.config.products:
                if self._stop:
                    break
                if self._key(product) in self._done:
                    continue
                result = self.monitor.check(product)
                if result.error:
                    log.debug("%s: %s", product.name, result.error)
                elif result.in_stock and result.variant is not None:
                    self._handle_in_stock(product, result)
                else:
                    log.debug("%s: not in stock", product.name)

                if self.checkout and self.purchases >= cap:
                    self.notifier.send("Fyodor done", f"Reached max purchases ({cap}).", level="success")
                    return 0
                self._sleep()
            if once:
                break
            self._sleep()
        return 0

    def _handle_in_stock(self, product: ProductConfig, result: StockResult) -> None:
        variant = result.variant
        price = float(variant.price) if variant.price else 0.0
        store = _store_label(product)
        item_id = self._item_ids.get(self._key(product))

        detected = detect_limit_from_text(result.raw_description)
        limit = clamp_quantity(
            product.desired_quantity,
            detected_limit=detected,
            configured_cap=product.max_per_customer,
            variant_available_qty=variant.inventory_quantity,
        ).quantity

        if item_id:
            repo.record_price(item_id, price, in_stock=True, limit=detected or product.max_per_customer)

        market = self._market_estimate(product)
        inputs = CostInputs(
            buy_price=price, quantity=product.desired_quantity,
            sales_tax_rate=product.sales_tax_rate, shipping_in=product.shipping_in,
            shipping_out=product.shipping_out, marketplace=product.resale_marketplace,
        )
        rec = evaluate(
            inputs=inputs, market=market, thresholds=self.thresholds, risk=self.risk,
            category=product.category, store=store, limit_quantity=limit,
        )

        if item_id:
            repo.record_opportunity(
                item_id, verdict=rec.verdict.value, buy_price=price, quantity=rec.quantity,
                resale_estimate=market.median_price, net_profit=rec.profit.net_profit_per_unit,
                roi=rec.profit.roi, confidence=market.confidence,
                sell_through_risk=market.sell_through_risk, reasons=rec.summary(),
                requires_manual=rec.requires_manual_approval,
            )

        self._alert(product, store, price, rec)

        if rec.verdict == Verdict.BUY and rec.quantity >= 1:
            self._maybe_buy(product, store, variant, rec)

    def _market_estimate(self, product: ProductConfig) -> MarketEstimate:
        if product.sold_prices:
            return estimate_from_prices(product.sold_prices)
        if product.manual_resale_estimate > 0:
            r = product.manual_resale_estimate
            return MarketEstimate(
                sample_size=1, median_price=r, mean_price=r, low_price=r, high_price=r,
                coef_variation=0.5, recent_velocity_per_week=1.0, confidence=0.4,
                sell_through_risk="medium", time_to_sell_days=None,
            )
        return estimate_from_prices([])

    def _alert(self, product, store, price, rec) -> None:
        level = {"BUY": "success", "WATCH": "warn", "SKIP": "info"}[rec.verdict.value]
        body = (
            f"{product.name} @ {store} — IN STOCK ${price:.2f}\n"
            f"Verdict: {rec.verdict.value}{' (manual approval)' if rec.requires_manual_approval else ''}\n"
            f"Resale≈${rec.market.median_price:.2f} | Net ${rec.profit.net_profit_per_unit:.2f}/unit | "
            f"ROI {rec.profit.roi*100:.0f}% | Conf {rec.market.confidence:.2f} | Qty {rec.quantity}\n"
            f"Max buy ${rec.max_buy:.2f} | Min resale ${rec.min_resale:.2f}\n"
            f"{product.store_url}/products/{product.handle}\n"
            f"Why: {rec.summary()}"
        )
        self.notifier.send(
            f"{rec.verdict.value}: {product.name}", body, level=level,
            dedupe_key=f"{self._key(product)}|{rec.verdict.value}",
        )

    def _maybe_buy(self, product, store, variant, rec) -> None:
        # Daily spend guard.
        cap = self.config.risk.max_spend_per_day
        if cap is not None:
            projected = repo.spend_today() + rec.profit.buy_price * rec.quantity
            if projected > cap:
                self.notifier.send(
                    "Auto-buy blocked", f"{product.name}: daily spend cap ${cap:.2f} would be exceeded.",
                    level="warn",
                )
                return

        trusted = store in {s.lower() for s in self.config.modes.auto_buy_sources}
        if rec.requires_manual_approval or not trusted:
            reason = "low confidence" if rec.requires_manual_approval else f"'{store}' not in auto_buy_sources"
            self.notifier.send(
                "Manual confirmation needed",
                f"{product.name}: BUY recommended ({reason}). Open the link and confirm yourself.",
                level="warn",
            )
            self._done.add(self._key(product))
            return

        if self.paper:
            self._record_purchase(product, store, variant, rec, status="paper")
            self.notifier.send("Paper buy", f"Simulated purchase of {rec.quantity}x {product.name}.", level="success")
            self.purchases += 1
            self._done.add(self._key(product))
            return

        if not self.checkout:
            self._done.add(self._key(product))
            return

        res = self.checkout.purchase(product.store_url, variant.variant_id, rec.quantity)
        self._report_checkout(product, store, variant, rec, res)

    def _record_purchase(self, product, store, variant, rec, *, status: str) -> None:
        unit_cost = rec.profit.total_cost
        pid = repo.add_purchase(
            item_id=self._item_ids.get(self._key(product)), name=product.name, store=store,
            quantity=rec.quantity, unit_cost=unit_cost, status="purchased" if status == "paper" else status,
        )
        for _ in range(rec.quantity):
            repo.add_inventory(name=product.name, purchase_id=pid, cost_basis=unit_cost,
                               marketplace=product.resale_marketplace, status="in_stock")

    def _report_checkout(self, product, store, variant, rec, res) -> None:
        level = {
            CheckoutStatus.PURCHASED: "success", CheckoutStatus.CHALLENGE: "warn",
            CheckoutStatus.NEEDS_MANUAL: "warn", CheckoutStatus.OUT_OF_STOCK: "info",
            CheckoutStatus.ERROR: "error",
        }.get(res.status, "info")
        self.notifier.send(f"Checkout: {res.status.value}", f"{product.name} — {res.message}", level=level)
        if res.status == CheckoutStatus.PURCHASED:
            self._record_purchase(product, store, variant, rec, status="purchased")
            self.purchases += 1
            self._done.add(self._key(product))
        elif res.status in (CheckoutStatus.CHALLENGE, CheckoutStatus.NEEDS_MANUAL):
            self._done.add(self._key(product))

    def _sleep(self) -> None:
        base = self.config.poll.effective_interval()
        delay = base + random.uniform(0, max(0.0, self.config.poll.jitter_seconds))
        end = time.time() + delay
        while time.time() < end and not self._stop:
            time.sleep(min(0.5, end - time.time()))


# -- subcommands ----------------------------------------------------------

def _cmd_login(config: Config) -> int:
    from .checkout import _import_playwright

    sync_playwright = _import_playwright()
    cfg = config.checkout
    log.info("opening profile at %s — log in, save address/payment, then close it.", cfg.browser_profile_dir)
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(cfg.browser_profile_dir, headless=False)
        page = context.pages[0] if context.pages else context.new_page()
        if config.products:
            page.goto(config.products[0].store_url)
        try:
            page.wait_for_event("close", timeout=0)
        except Exception:  # noqa: BLE001
            pass
        context.close()
    return 0


def _cmd_web(args) -> int:
    import uvicorn

    init_db()
    uvicorn.run("fyodor.web.app:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fyodor",
        description="Compliant reselling automation: discover, score, alert, assist checkout.",
    )
    parser.add_argument("-c", "--config", default="config.yaml")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command")

    p_watch = sub.add_parser("watch", help="watch products, score opportunities, alert, assist checkout")
    p_watch.add_argument("--once", action="store_true")
    p_watch.add_argument("--dry-run", action="store_true", help="never touch a cart; alert + record only")

    p_web = sub.add_parser("web", help="run the dashboard web server")
    p_web.add_argument("--host", default="127.0.0.1")
    p_web.add_argument("--port", type=int, default=8000)
    p_web.add_argument("--reload", action="store_true")

    sub.add_parser("login", help="open the browser profile to sign in / save payment once")
    sub.add_parser("check", help="one-shot stock + recommendation pass (no checkout)")
    sub.add_parser("init-db", help="create database tables and exit")

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    if args.command == "init-db":
        init_db()
        log.info("database initialised")
        return 0
    if args.command == "web":
        return _cmd_web(args)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        log.error("config error: %s", exc)
        return 2

    if args.command == "login":
        return _cmd_login(config)

    app = Fyodor(config, dry_run=getattr(args, "dry_run", False))
    signal.signal(signal.SIGINT, app.request_stop)
    signal.signal(signal.SIGTERM, app.request_stop)

    if args.command == "check":
        app.dry_run = True
        app.checkout = None
        return app.run(once=True)
    return app.run(once=getattr(args, "once", False))


if __name__ == "__main__":
    sys.exit(main())
