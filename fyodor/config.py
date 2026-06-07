"""Configuration loading and validation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default) or default


class ConfigError(Exception):
    """Raised when the configuration file is missing or invalid."""


@dataclass
class PollConfig:
    interval_seconds: float = 8.0
    min_interval_seconds: float = 3.0
    jitter_seconds: float = 4.0
    timeout_seconds: float = 10.0

    def effective_interval(self) -> float:
        """The interval actually used, never below the hard floor."""
        return max(self.interval_seconds, self.min_interval_seconds)


@dataclass
class CheckoutConfig:
    enabled: bool = True
    browser_profile_dir: str = "./browser-profile"
    headless: bool = False
    hand_off_on_challenge: bool = True
    max_purchases_per_run: int = 1
    page_timeout_seconds: float = 30.0


@dataclass
class NotifyConfig:
    discord_webhook_url: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    email_to: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    console: bool = True
    dedupe_minutes: int = 30

    def resolve_secrets(self) -> None:
        """Fill blank secret fields from the environment (preferred for secrets)."""
        self.discord_webhook_url = self.discord_webhook_url or _env("FYODOR_DISCORD_WEBHOOK")
        self.telegram_bot_token = self.telegram_bot_token or _env("FYODOR_TELEGRAM_TOKEN")
        self.telegram_chat_id = self.telegram_chat_id or _env("FYODOR_TELEGRAM_CHAT_ID")
        self.smtp_user = self.smtp_user or _env("FYODOR_SMTP_USER")
        self.smtp_password = self.smtp_password or _env("FYODOR_SMTP_PASSWORD")


@dataclass
class ThresholdsConfig:
    min_profit: float = 15.0
    min_roi: float = 0.25
    min_confidence: float = 0.5
    watch_confidence: float = 0.3
    require_data: bool = True


@dataclass
class RiskConfig:
    max_spend_per_day: float | None = None
    max_spend_per_product: float | None = None
    max_quantity_per_product: int | None = None
    max_total_exposure: float | None = None
    require_manual_below_confidence: float = 0.5
    category_blacklist: list[str] = field(default_factory=list)
    store_blacklist: list[str] = field(default_factory=list)


@dataclass
class ModesConfig:
    # Mutually-reinforcing safety modes.
    dry_run: bool = False           # never touch a cart; alert + record only
    paper: bool = False             # simulate purchases into the DB
    alert_only: bool = False        # discovery + alerts, no checkout at all
    auto_buy_sources: list[str] = field(default_factory=list)  # stores trusted for auto-buy


@dataclass
class ProductConfig:
    name: str
    store_url: str
    handle: str = ""
    desired_quantity: int = 1
    variant_title: str | None = None
    variant_id: int | None = None
    max_per_customer: int | None = None
    # Identifiers for non-Shopify providers (Best Buy, etc.).
    store: str = ""              # explicit provider override, e.g. "bestbuy"
    upc: str = ""
    sku: str = ""
    model: str = ""
    # Resale / profitability inputs (used to score opportunities + recommend).
    category: str = ""
    resale_marketplace: str = "ebay"
    manual_resale_estimate: float = 0.0
    sold_prices: list[float] = field(default_factory=list)
    sales_tax_rate: float = 0.0
    shipping_in: float = 0.0
    shipping_out: float = 0.0
    max_buy_price: float | None = None

    def __post_init__(self) -> None:
        self.store_url = self.store_url.rstrip("/")
        if not self.store_url.startswith("http"):
            raise ConfigError(f"product '{self.name}': store_url must be an http(s) URL")
        if self.desired_quantity < 1:
            raise ConfigError(f"product '{self.name}': desired_quantity must be >= 1")


@dataclass
class Config:
    poll: PollConfig = field(default_factory=PollConfig)
    checkout: CheckoutConfig = field(default_factory=CheckoutConfig)
    notify: NotifyConfig = field(default_factory=NotifyConfig)
    thresholds: ThresholdsConfig = field(default_factory=ThresholdsConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    modes: ModesConfig = field(default_factory=ModesConfig)
    products: list[ProductConfig] = field(default_factory=list)


def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key) or {}
    if not isinstance(value, dict):
        raise ConfigError(f"'{key}' section must be a mapping")
    return value


def load_config(path: str | Path) -> Config:
    """Load and validate a YAML config file into a :class:`Config`."""
    path = Path(path)
    if not path.exists():
        raise ConfigError(
            f"config file not found: {path}\n"
            "Copy config.example.yaml to config.yaml and edit it."
        )

    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ConfigError("top-level config must be a mapping")

    raw_products = data.get("products") or []
    if not isinstance(raw_products, list):
        raise ConfigError("'products' must be a list")

    products: list[ProductConfig] = []
    for i, item in enumerate(raw_products):
        if not isinstance(item, dict):
            raise ConfigError(f"products[{i}] must be a mapping")
        try:
            products.append(ProductConfig(**item))
        except TypeError as exc:
            raise ConfigError(f"products[{i}]: {exc}") from exc

    config = Config(
        poll=PollConfig(**_section(data, "poll")),
        checkout=CheckoutConfig(**_section(data, "checkout")),
        notify=NotifyConfig(**_section(data, "notify")),
        thresholds=ThresholdsConfig(**_section(data, "thresholds")),
        risk=RiskConfig(**_section(data, "risk")),
        modes=ModesConfig(**_section(data, "modes")),
        products=products,
    )
    config.notify.resolve_secrets()

    # Sanity: never allow the polite-polling floor to be bypassed via config.
    if config.poll.min_interval_seconds < 1:
        config.poll.min_interval_seconds = 1.0
    return config
