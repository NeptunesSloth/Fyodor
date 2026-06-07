"""SQLAlchemy ORM models for watchlist, prices, opportunities, inventory, sales."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WatchItem(Base):
    """A product the user wants to track."""

    __tablename__ = "watch_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    store: Mapped[str] = mapped_column(String(100))
    url: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(100), default="")
    # Identifiers for matching across marketplaces.
    upc: Mapped[str] = mapped_column(String(64), default="")
    sku: Mapped[str] = mapped_column(String(120), default="")
    model: Mapped[str] = mapped_column(String(120), default="")
    keywords: Mapped[str] = mapped_column(Text, default="")

    # Buying parameters.
    desired_quantity: Mapped[int] = mapped_column(Integer, default=1)
    max_per_customer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_buy_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    resale_marketplace: Mapped[str] = mapped_column(String(60), default="ebay")
    sales_tax_rate: Mapped[float] = mapped_column(Float, default=0.0)
    shipping_in: Mapped[float] = mapped_column(Float, default=0.0)
    shipping_out: Mapped[float] = mapped_column(Float, default=0.0)
    # Manual resale override; if 0, use market data.
    manual_resale_estimate: Mapped[float] = mapped_column(Float, default=0.0)

    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    prices: Mapped[list["PricePoint"]] = relationship(back_populates="item", cascade="all, delete-orphan")
    opportunities: Mapped[list["Opportunity"]] = relationship(back_populates="item", cascade="all, delete-orphan")


class PricePoint(Base):
    """Historical price/stock observation for a watch item."""

    __tablename__ = "price_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("watch_items.id"))
    price: Mapped[float] = mapped_column(Float)
    in_stock: Mapped[bool] = mapped_column(default=False)
    limit_per_customer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    item: Mapped[WatchItem] = relationship(back_populates="prices")


class Opportunity(Base):
    """A scored buy opportunity emitted by the recommendation engine."""

    __tablename__ = "opportunities"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("watch_items.id"))
    verdict: Mapped[str] = mapped_column(String(10))           # BUY / WATCH / SKIP
    buy_price: Mapped[float] = mapped_column(Float)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    resale_estimate: Mapped[float] = mapped_column(Float, default=0.0)
    net_profit: Mapped[float] = mapped_column(Float, default=0.0)
    roi: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    sell_through_risk: Mapped[str] = mapped_column(String(10), default="high")
    reasons: Mapped[str] = mapped_column(Text, default="")
    requires_manual: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    item: Mapped[WatchItem] = relationship(back_populates="opportunities")


class Purchase(Base):
    """A completed (or attempted) purchase."""

    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int | None] = mapped_column(ForeignKey("watch_items.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(300))
    store: Mapped[str] = mapped_column(String(100), default="")
    order_number: Mapped[str] = mapped_column(String(120), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(30), default="purchased")  # purchased/needs_manual/...
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class InventoryItem(Base):
    """An owned unit available to sell or being sold."""

    __tablename__ = "inventory_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    purchase_id: Mapped[int | None] = mapped_column(ForeignKey("purchases.id"), nullable=True)
    cost_basis: Mapped[float] = mapped_column(Float, default=0.0)
    listed_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    marketplace: Mapped[str] = mapped_column(String(60), default="")
    status: Mapped[str] = mapped_column(String(30), default="in_stock")  # in_stock/listed/sold
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Sale(Base):
    """A sold unit with realised profit."""

    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(primary_key=True)
    inventory_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_items.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(300))
    marketplace: Mapped[str] = mapped_column(String(60), default="")
    sold_price: Mapped[float] = mapped_column(Float, default=0.0)
    fees: Mapped[float] = mapped_column(Float, default=0.0)
    cost_basis: Mapped[float] = mapped_column(Float, default=0.0)
    net_profit: Mapped[float] = mapped_column(Float, default=0.0)
    days_held: Mapped[int] = mapped_column(Integer, default=0)
    sold_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AlertLog(Base):
    """Record of every alert sent (for the alerts history view + dedupe)."""

    __tablename__ = "alert_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, default="")
    level: Mapped[str] = mapped_column(String(20), default="info")
    dedupe_key: Mapped[str] = mapped_column(String(200), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
