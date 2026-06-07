from fyodor.market import estimate_from_prices, estimate_market
from fyodor.profitability import CostInputs
from fyodor.recommend import RiskControls, Thresholds, Verdict, evaluate


def _market(prices):
    return estimate_from_prices(prices)


def test_strong_opportunity_is_buy():
    inputs = CostInputs(buy_price=100, marketplace="facebook")  # 0% fees, local
    market = _market([160, 162, 158, 165, 159, 161, 163, 160, 158, 164, 162, 160])
    rec = evaluate(inputs=inputs, market=market, thresholds=Thresholds(), risk=RiskControls())
    assert rec.verdict == Verdict.BUY
    assert rec.profit.net_profit_per_unit > 15


def test_no_data_skips_when_required():
    inputs = CostInputs(buy_price=100)
    rec = evaluate(inputs=inputs, market=estimate_market([]), thresholds=Thresholds(require_data=True), risk=RiskControls())
    assert rec.verdict == Verdict.SKIP
    assert rec.requires_manual_approval


def test_thin_margin_is_watch_or_skip():
    inputs = CostInputs(buy_price=100, marketplace="ebay")
    market = _market([108, 110, 105, 112])  # barely above cost after fees
    rec = evaluate(inputs=inputs, market=market, thresholds=Thresholds(), risk=RiskControls())
    assert rec.verdict in (Verdict.WATCH, Verdict.SKIP)


def test_respects_store_limit_quantity():
    inputs = CostInputs(buy_price=50, quantity=10, marketplace="facebook")
    market = _market([100, 102, 98, 101, 99, 100, 103, 100, 100, 101, 99, 100])
    rec = evaluate(inputs=inputs, market=market, thresholds=Thresholds(), risk=RiskControls(), limit_quantity=2)
    assert rec.quantity == 2


def test_blacklisted_category_skips():
    inputs = CostInputs(buy_price=10, marketplace="facebook")
    market = _market([100, 102, 98, 101, 99, 100, 103, 100, 100, 101, 99, 100])
    rec = evaluate(
        inputs=inputs, market=market, thresholds=Thresholds(),
        risk=RiskControls(category_blacklist=["tickets"]), category="tickets",
    )
    assert rec.verdict == Verdict.SKIP


def test_max_spend_per_product_blocks():
    inputs = CostInputs(buy_price=300, quantity=2, marketplace="facebook")
    market = _market([500, 510, 505, 495, 500, 502, 498, 500, 501, 499, 503, 500])
    rec = evaluate(
        inputs=inputs, market=market, thresholds=Thresholds(),
        risk=RiskControls(max_spend_per_product=400), limit_quantity=2,
    )
    assert rec.verdict == Verdict.SKIP
