"""Thin data-access helpers shared by the web app and background services."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from .db import session_scope
from .models import AlertLog, InventoryItem, Opportunity, PricePoint, Purchase, Sale, WatchItem


# -- watchlist ------------------------------------------------------------

def list_watch_items(active_only: bool = False) -> list[WatchItem]:
    with session_scope() as s:
        stmt = select(WatchItem).order_by(WatchItem.created_at.desc())
        if active_only:
            stmt = stmt.where(WatchItem.active.is_(True))
        return list(s.scalars(stmt))


def add_watch_item(**fields) -> int:
    with session_scope() as s:
        item = WatchItem(**fields)
        s.add(item)
        s.flush()
        return item.id


def get_watch_item(item_id: int) -> WatchItem | None:
    with session_scope() as s:
        return s.get(WatchItem, item_id)


def get_or_create_watch_item(name: str, store: str, **defaults) -> int:
    """Idempotently ensure a watch item exists (matched on name+store). Returns id."""
    with session_scope() as s:
        existing = s.scalars(
            select(WatchItem).where(WatchItem.name == name, WatchItem.store == store)
        ).first()
        if existing:
            return existing.id
        item = WatchItem(name=name, store=store, **defaults)
        s.add(item)
        s.flush()
        return item.id


def set_active(item_id: int, active: bool) -> None:
    with session_scope() as s:
        if item := s.get(WatchItem, item_id):
            item.active = active


def delete_watch_item(item_id: int) -> None:
    with session_scope() as s:
        if item := s.get(WatchItem, item_id):
            s.delete(item)


# -- observations & opportunities ----------------------------------------

def record_price(item_id: int, price: float, in_stock: bool, limit: int | None = None) -> None:
    with session_scope() as s:
        s.add(PricePoint(item_id=item_id, price=price, in_stock=in_stock, limit_per_customer=limit))


def record_opportunity(item_id: int, **fields) -> int:
    with session_scope() as s:
        opp = Opportunity(item_id=item_id, **fields)
        s.add(opp)
        s.flush()
        return opp.id


def list_opportunities(limit: int = 50, verdict: str | None = None) -> list[Opportunity]:
    with session_scope() as s:
        stmt = select(Opportunity).order_by(Opportunity.created_at.desc()).limit(limit)
        if verdict:
            stmt = stmt.where(Opportunity.verdict == verdict)
        return list(s.scalars(stmt))


# -- purchases / inventory / sales ---------------------------------------

def add_purchase(**fields) -> int:
    with session_scope() as s:
        p = Purchase(**fields)
        s.add(p)
        s.flush()
        return p.id


def list_purchases(limit: int = 100) -> list[Purchase]:
    with session_scope() as s:
        return list(s.scalars(select(Purchase).order_by(Purchase.created_at.desc()).limit(limit)))


def add_inventory(**fields) -> int:
    with session_scope() as s:
        inv = InventoryItem(**fields)
        s.add(inv)
        s.flush()
        return inv.id


def list_inventory(status: str | None = None) -> list[InventoryItem]:
    with session_scope() as s:
        stmt = select(InventoryItem).order_by(InventoryItem.acquired_at.desc())
        if status:
            stmt = stmt.where(InventoryItem.status == status)
        return list(s.scalars(stmt))


def record_sale(inventory_id: int | None, **fields) -> int:
    with session_scope() as s:
        sale = Sale(inventory_id=inventory_id, **fields)
        s.add(sale)
        if inventory_id and (inv := s.get(InventoryItem, inventory_id)):
            inv.status = "sold"
        s.flush()
        return sale.id


def list_sales(limit: int = 200) -> list[Sale]:
    with session_scope() as s:
        return list(s.scalars(select(Sale).order_by(Sale.sold_at.desc()).limit(limit)))


def list_alerts(limit: int = 100) -> list[AlertLog]:
    with session_scope() as s:
        return list(s.scalars(select(AlertLog).order_by(AlertLog.created_at.desc()).limit(limit)))


# -- analytics ------------------------------------------------------------

def pnl_summary() -> dict:
    with session_scope() as s:
        total_profit = s.scalar(select(func.coalesce(func.sum(Sale.net_profit), 0.0))) or 0.0
        total_revenue = s.scalar(select(func.coalesce(func.sum(Sale.sold_price), 0.0))) or 0.0
        units_sold = s.scalar(select(func.count(Sale.id))) or 0
        wins = s.scalar(select(func.count(Sale.id)).where(Sale.net_profit > 0)) or 0
        losses = s.scalar(select(func.count(Sale.id)).where(Sale.net_profit <= 0)) or 0
        invested = s.scalar(
            select(func.coalesce(func.sum(InventoryItem.cost_basis), 0.0)).where(
                InventoryItem.status != "sold"
            )
        ) or 0.0
        open_units = s.scalar(
            select(func.count(InventoryItem.id)).where(InventoryItem.status != "sold")
        ) or 0
        return {
            "total_profit": round(total_profit, 2),
            "total_revenue": round(total_revenue, 2),
            "units_sold": units_sold,
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / units_sold, 3) if units_sold else 0.0,
            "open_inventory_value": round(invested, 2),
            "open_units": open_units,
        }


def spend_today() -> float:
    with session_scope() as s:
        start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        total = s.scalar(
            select(func.coalesce(func.sum(Purchase.unit_cost * Purchase.quantity), 0.0)).where(
                Purchase.created_at >= start, Purchase.status == "purchased"
            )
        )
        return round(total or 0.0, 2)
