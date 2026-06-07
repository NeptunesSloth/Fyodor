"""FastAPI web dashboard + JSON API for Fyodor."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import repository as repo
from ..db import init_db
from ..fees import get_fee_model
from ..market import MarketEstimate
from ..profitability import CostInputs, compute, min_acceptable_resale, recommended_max_buy
from ..recommend import RiskControls, Thresholds, Verdict, evaluate

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Fyodor", description="Compliant reselling automation dashboard", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# -- pages ----------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "pnl": repo.pnl_summary(),
            "spend_today": repo.spend_today(),
            "opportunities": repo.list_opportunities(limit=25),
            "alerts": repo.list_alerts(limit=10),
        },
    )


@app.get("/watchlist", response_class=HTMLResponse)
def watchlist(request: Request):
    return templates.TemplateResponse(
        request, "watchlist.html", {"items": repo.list_watch_items()}
    )


@app.post("/watchlist/add")
def watchlist_add(
    name: str = Form(...),
    store: str = Form(""),
    url: str = Form(""),
    category: str = Form(""),
    desired_quantity: int = Form(1),
    max_per_customer: int = Form(0),
    max_buy_price: float = Form(0.0),
    resale_marketplace: str = Form("ebay"),
    manual_resale_estimate: float = Form(0.0),
):
    repo.add_watch_item(
        name=name, store=store, url=url, category=category,
        desired_quantity=desired_quantity,
        max_per_customer=max_per_customer or None,
        max_buy_price=max_buy_price or None,
        resale_marketplace=resale_marketplace,
        manual_resale_estimate=manual_resale_estimate,
    )
    return RedirectResponse("/watchlist", status_code=303)


@app.post("/watchlist/{item_id}/delete")
def watchlist_delete(item_id: int):
    repo.delete_watch_item(item_id)
    return RedirectResponse("/watchlist", status_code=303)


@app.get("/inventory", response_class=HTMLResponse)
def inventory(request: Request):
    return templates.TemplateResponse(
        request,
        "inventory.html",
        {
            "inventory": repo.list_inventory(),
            "sales": repo.list_sales(limit=50),
            "purchases": repo.list_purchases(limit=50),
        },
    )


@app.get("/calculator", response_class=HTMLResponse)
def calculator(request: Request):
    return templates.TemplateResponse(request, "calculator.html", {})


@app.get("/alerts", response_class=HTMLResponse)
def alerts(request: Request):
    return templates.TemplateResponse(
        request, "alerts.html", {"alerts": repo.list_alerts(limit=200)}
    )


# -- JSON API -------------------------------------------------------------

@app.get("/api/pnl")
def api_pnl():
    return repo.pnl_summary()


@app.get("/api/opportunities")
def api_opportunities(verdict: str | None = None, limit: int = 50):
    rows = repo.list_opportunities(limit=limit, verdict=verdict)
    return [
        {
            "id": o.id, "item_id": o.item_id, "verdict": o.verdict, "buy_price": o.buy_price,
            "quantity": o.quantity, "resale_estimate": o.resale_estimate, "net_profit": o.net_profit,
            "roi": o.roi, "confidence": o.confidence, "risk": o.sell_through_risk,
            "reasons": o.reasons, "requires_manual": o.requires_manual,
        }
        for o in rows
    ]


@app.post("/api/calculate")
def api_calculate(payload: dict):
    """Profit calculator + recommendation for a single hypothetical buy.

    Body: {buy_price, resale_price?, quantity?, marketplace?, sales_tax_rate?,
           shipping_in?, shipping_out?, sold_prices?:[...], limit_per_customer?}
    """
    buy = float(payload.get("buy_price", 0))
    qty = int(payload.get("quantity", 1))
    marketplace = payload.get("marketplace", "ebay")
    inputs = CostInputs(
        buy_price=buy,
        quantity=qty,
        sales_tax_rate=float(payload.get("sales_tax_rate", 0.0)),
        shipping_in=float(payload.get("shipping_in", 0.0)),
        shipping_out=float(payload.get("shipping_out", 0.0)),
        marketplace=marketplace,
    )

    sold = [float(p) for p in payload.get("sold_prices", []) if float(p) > 0]
    if sold:
        sold_sorted = sorted(sold)
        median = sold_sorted[len(sold_sorted) // 2]
        market = MarketEstimate(
            sample_size=len(sold), median_price=median, mean_price=sum(sold) / len(sold),
            low_price=min(sold), high_price=max(sold), coef_variation=0.1,
            recent_velocity_per_week=2.0, confidence=min(0.5 + len(sold) / 20, 0.95),
            sell_through_risk="low", time_to_sell_days=3.5,
        )
        resale = median
    else:
        resale = float(payload.get("resale_price", 0.0))
        market = MarketEstimate(
            sample_size=0, median_price=resale, mean_price=resale, low_price=resale,
            high_price=resale, coef_variation=1.0, recent_velocity_per_week=0.0,
            confidence=0.0 if resale == 0 else 0.4, sell_through_risk="high", time_to_sell_days=None,
        )

    th = Thresholds()
    rec = evaluate(
        inputs=inputs, market=market, thresholds=th, risk=RiskControls(),
        limit_quantity=payload.get("limit_per_customer"),
    )
    result = compute(inputs, resale)
    return JSONResponse(
        {
            "verdict": rec.verdict.value,
            "profit": result.as_dict(),
            "min_acceptable_resale": round(min_acceptable_resale(inputs, min_roi=th.min_roi, min_profit=th.min_profit), 2),
            "recommended_max_buy": round(
                recommended_max_buy(
                    resale, marketplace=marketplace, sales_tax_rate=inputs.sales_tax_rate,
                    shipping_in=inputs.shipping_in, shipping_out=inputs.shipping_out, min_roi=th.min_roi,
                ),
                2,
            ),
            "fee_model": get_fee_model(marketplace).name,
            "confidence": market.confidence,
            "quantity": rec.quantity,
            "requires_manual_approval": rec.requires_manual_approval,
            "reasons": rec.reasons,
        }
    )


@app.get("/api/health")
def api_health():
    return {"status": "ok", "verdicts": [v.value for v in Verdict]}
