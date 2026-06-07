import httpx

from fyodor.config import ProductConfig
from fyodor.providers import Support, coverage_report, get_retail_provider, get_sold_provider, resolve_store
from fyodor.providers.base import UnavailableRetailProvider
from fyodor.providers.bestbuy import BestBuyProvider
from fyodor.providers.ebay import EbaySoldDataProvider
from fyodor.providers.registry import CAPABILITIES


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


# -- registry -------------------------------------------------------------

def test_every_requested_store_is_registered():
    wanted = {
        "amazon", "walmart", "target", "bestbuy", "ebay", "facebook", "offerup",
        "stockx", "goat", "mercari", "gamestop", "lego",
    }
    assert wanted.issubset(set(CAPABILITIES))


def test_aliases_resolve():
    assert resolve_store("best buy").store == "bestbuy"
    assert resolve_store("facebook marketplace").store == "facebook"


def test_unknown_store_defaults_to_shopify():
    p = get_retail_provider("shop.somerandomstore.com")
    assert p.name == "shopify"


def test_prohibited_store_returns_unavailable_not_scraper():
    p = get_retail_provider("facebook")
    assert isinstance(p, UnavailableRetailProvider)
    status = p.check(ProductConfig(name="x", store_url="https://facebook.com"))
    assert status.error and "prohibited" in status.error.lower()


def test_coverage_report_shape():
    rows = coverage_report()
    assert all({"store", "kind", "support", "requires", "note"} <= set(r) for r in rows)


# -- Best Buy (official API, mocked) --------------------------------------

def test_bestbuy_in_stock_parsing():
    def handler(request):
        assert "apiKey=testkey" in str(request.url)
        return httpx.Response(200, json={"products": [
            {"sku": 123, "name": "Widget", "salePrice": 99.99,
             "onlineAvailability": True, "orderable": "Available", "url": "http://bb/x"}
        ]})

    bb = BestBuyProvider(client=_client(handler), api_key="testkey")
    status = bb.check(ProductConfig(name="Widget", store_url="https://bestbuy.com", sku="123"))
    assert status.in_stock is True
    assert status.price == 99.99
    assert status.variant_id == 123


def test_bestbuy_requires_key():
    bb = BestBuyProvider(client=_client(lambda r: httpx.Response(200, json={})), api_key="")
    status = bb.check(ProductConfig(name="x", store_url="https://bestbuy.com"))
    assert status.error and "FYODOR_BESTBUY_API_KEY" in status.error


# -- eBay sold data (official API, mocked) --------------------------------

def test_ebay_sold_data_parsing():
    def handler(request):
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})
        return httpx.Response(200, json={"itemSales": [
            {"lastSoldPrice": {"value": "150.00", "currency": "USD"}, "lastSoldDate": "2026-05-01T00:00:00Z"},
            {"lastSoldPrice": {"value": "160.00", "currency": "USD"}, "lastSoldDate": "2026-05-10T00:00:00Z"},
        ]})

    ebay = EbaySoldDataProvider(client=_client(handler), client_id="id", client_secret="secret")
    records = ebay.recent_sold("Some Sneaker")
    assert len(records) == 2
    assert {r.price for r in records} == {150.0, 160.0}
    assert all(r.marketplace == "ebay" for r in records)


def test_ebay_not_configured_returns_empty():
    ebay = EbaySoldDataProvider(client=_client(lambda r: httpx.Response(500)), client_id="", client_secret="")
    assert ebay.recent_sold("anything") == []


def test_ebay_insights_403_handled():
    def handler(request):
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})
        return httpx.Response(403, json={"errors": []})

    ebay = EbaySoldDataProvider(client=_client(handler), client_id="id", client_secret="secret")
    assert ebay.recent_sold("x") == []


def test_get_sold_provider_default_is_ebay():
    assert get_sold_provider("ebay").name == "ebay"
