from fyodor import repository as repo
from fyodor.db import init_db


def setup_module(_module):
    init_db()


def test_get_or_create_is_idempotent():
    a = repo.get_or_create_watch_item("Widget", "walmart", category="tools")
    b = repo.get_or_create_watch_item("Widget", "walmart")
    assert a == b


def test_price_and_opportunity_roundtrip():
    item_id = repo.get_or_create_watch_item("Gadget", "target")
    repo.record_price(item_id, 99.99, in_stock=True, limit=2)
    repo.record_opportunity(
        item_id, verdict="BUY", buy_price=99.99, quantity=2, resale_estimate=160,
        net_profit=40, roi=0.4, confidence=0.7, sell_through_risk="low",
        reasons="looks good", requires_manual=False,
    )
    opps = repo.list_opportunities(limit=10, verdict="BUY")
    assert any(o.item_id == item_id for o in opps)


def test_pnl_summary_reflects_sales():
    inv = repo.add_inventory(name="Sneaker", cost_basis=120, marketplace="stockx")
    repo.record_sale(inv, name="Sneaker", marketplace="stockx", sold_price=200,
                     fees=20, cost_basis=120, net_profit=60, days_held=4)
    summary = repo.pnl_summary()
    assert summary["units_sold"] >= 1
    assert summary["total_profit"] >= 60
    assert summary["wins"] >= 1
