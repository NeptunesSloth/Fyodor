"""Linked Scryfall images: the Magic card back and the mana symbols, fetched into the host's cache, served, refused when unknown."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.cards.images import CARD_BACK_URL, ImageStore
from app.cards.linked import download_symbols

SVG = b"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><circle fill='#F8F6D8' cx='50' cy='50' r='50'/></svg>"
SYMBOLOGY = {
    "object": "list", "has_more": False,
    "data": [
        {"symbol": "{W}", "svg_uri": "https://svgs.scryfall.io/card-symbols/W.svg", "english": "one white mana"},
        {"symbol": "{W/U}", "svg_uri": "https://svgs.scryfall.io/card-symbols/WU.svg", "english": "one white or blue mana"},
        {"symbol": "{T}", "svg_uri": "https://svgs.scryfall.io/card-symbols/T.svg", "english": "tap this permanent"},
        {"symbol": "{½}", "svg_uri": "https://svgs.scryfall.io/card-symbols/HALF.svg", "english": "one-half generic mana"},
        # refused: a script inside, a path out of the cache, not https, an answer that isn't an SVG
        {"symbol": "{EVIL}", "svg_uri": "https://svgs.scryfall.io/card-symbols/EVIL.svg", "english": "x"},
        {"symbol": "{UP}", "svg_uri": "https://svgs.scryfall.io/card-symbols/../../app.svg", "english": "x"},
        {"symbol": "{HTTP}", "svg_uri": "http://svgs.scryfall.io/card-symbols/HTTP.svg", "english": "x"},
        {"symbol": "{HTML}", "svg_uri": "https://svgs.scryfall.io/card-symbols/HTML.svg", "english": "x"},
        {"symbol": "{ELSEWHERE}", "svg_uri": "https://example.com/card-symbols/ELSEWHERE.svg", "english": "x"},
    ],
}


def scryfall(calls: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path.endswith("/symbology"):
            return httpx.Response(200, json=SYMBOLOGY)
        if str(request.url) == CARD_BACK_URL:
            return httpx.Response(200, content=b"\xff\xd8back")
        name = request.url.path.rsplit("/", 1)[-1]
        if name == "EVIL.svg":
            return httpx.Response(200, content=b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>")
        if name == "HTML.svg":
            return httpx.Response(200, content=b"<html><body>Not found</body></html>")
        if name.endswith(".svg"):
            return httpx.Response(200, content=SVG, headers={"Content-Type": "image/svg+xml"})
        return httpx.Response(404)

    return handler


def fake_client(calls: list[str]):
    return lambda user_agent, timeout=60.0: httpx.Client(transport=httpx.MockTransport(scryfall(calls)))


def test_symbols_are_fetched_once_and_only_safe_ones_kept(tmp_path: Path):
    store = ImageStore(tmp_path)
    calls: list[str] = []
    with fake_client(calls)("test") as http:
        assert download_symbols(http, store, "https://api.scryfall.com") == 4
    index = store.symbol_index()
    assert {k: v["svg"] for k, v in index.items()} == {"W": "W", "W/U": "WU", "T": "T", "½": "HALF"}
    assert index["W/U"]["english"] == "one white or blue mana"
    assert sorted(p.name for p in store.symbols_dir().iterdir() if p.suffix == ".svg") == ["HALF.svg", "T.svg", "W.svg", "WU.svg"]
    assert not any("app.svg" in c or c.startswith("http://") or "example.com" in c for c in calls)
    # a second time: only the list is asked for (new sets bring new symbols), nothing cached is downloaded again
    calls.clear()
    with fake_client(calls)("test") as http:
        assert download_symbols(http, store, "https://api.scryfall.com") == 4
    assert [c for c in calls if c.endswith(".svg") and "EVIL" not in c and "HTML" not in c] == []


def test_symbols_are_served_from_the_cache_and_unknown_codes_refused(client, settings):
    services = client.app.state.services
    assert client.get("/api/symbols").json() == {"symbols": {}}  # nothing cached (and no download in the tests)
    assert client.get("/api/symbols/W.svg").status_code == 404
    with fake_client([])("test") as http:
        download_symbols(http, services.images, "https://api.scryfall.com")
    listed = client.get("/api/symbols").json()["symbols"]
    assert listed["W"] == {"svg": "W", "english": "one white mana"} and listed["½"]["svg"] == "HALF"
    res = client.get("/api/symbols/WU.svg")
    assert res.status_code == 200 and res.content == SVG
    assert res.headers["content-type"].startswith("image/svg+xml")
    assert "default-src 'none'" in res.headers["content-security-policy"]  # opened on its own, an SVG runs nothing
    # only codes from the cached list: not another file in the folder, not a lowercase spelling, no way out of it
    (services.images.symbols_dir() / "STRAY.svg").write_bytes(SVG)
    for bad in ("STRAY", "w", "EVIL", "..%2Findex", "..%2F..%2Fapp", "%2E%2E", "W%00"):
        assert client.get(f"/api/symbols/{bad}.svg").status_code == 404, bad
    assert client.get("/api/symbols/../app.sqlite").status_code == 404
    assert client.get("/api/symbols/W.png").status_code == 404


def test_a_card_database_update_also_fetches_the_card_back_and_symbols(client, monkeypatch: pytest.MonkeyPatch):
    services = client.app.state.services
    calls: list[str] = []
    services.http_client = fake_client(calls)
    assert client.get("/api/images/card-back").status_code == 404

    def update(*_: Any, **__: Any) -> str:
        return "Card data is already current."

    # the bulk download is test_card_update's subject; here only what comes with it
    monkeypatch.setattr("app.cards.updater.update", update)
    assert client.post("/api/card-data/update").status_code == 202
    job: dict[str, Any] = {}
    deadline = time.time() + 20
    while time.time() < deadline:
        job = client.get("/api/card-data").json()["job"]
        if job and job["state"] != "running":
            break
        time.sleep(0.05)
    assert job["state"] == "done", job
    assert CARD_BACK_URL in calls and any(c.endswith("/symbology") for c in calls)
    assert client.get("/api/images/card-back").content == b"\xff\xd8back"
    assert "W" in client.get("/api/symbols").json()["symbols"]


def test_missing_assets_are_fetched_at_start_and_on_demand_when_online(settings, card_db, monkeypatch: pytest.MonkeyPatch):
    from fastapi.testclient import TestClient

    from app.cards import linked
    from app.main import create_app

    calls: list[str] = []
    monkeypatch.setattr(linked, "DOWNLOADS", True)
    monkeypatch.setattr("app.services.make_client", fake_client(calls))
    with TestClient(create_app(settings)) as c:
        services = c.app.state.services
        deadline = time.time() + 20
        while services.linked.busy() and time.time() < deadline:
            time.sleep(0.02)
        assert CARD_BACK_URL in calls and any(u.endswith("/symbology") for u in calls)  # at start: both were missing
        assert c.get("/api/images/card-back").status_code == 200
        # all there: asking again fetches nothing
        calls.clear()
        services.linked.kick()
        assert calls == []
        # one goes missing: the next request for it brings it back (in the background; inline here), at most so often
        services.linked.synchronous = True
        services.linked.last_try = None
        services.images.card_back_path().unlink()
        assert c.get("/api/images/card-back").status_code == 200
        assert calls.count(CARD_BACK_URL) == 1
        services.images.card_back_path().unlink()
        assert c.get("/api/images/card-back").status_code == 404  # tried a moment ago: not again yet
        assert calls.count(CARD_BACK_URL) == 1


def test_nothing_is_fetched_when_the_network_is_off(settings, card_db, monkeypatch: pytest.MonkeyPatch):
    from fastapi.testclient import TestClient

    from app.cards import linked
    from app.main import create_app

    calls: list[str] = []
    monkeypatch.setattr(linked, "DOWNLOADS", True)
    monkeypatch.setattr("app.services.make_client", fake_client(calls))
    object.__setattr__(settings, "allow_network", False)
    with TestClient(create_app(settings)) as c:
        c.app.state.services.linked.synchronous = True
        assert c.get("/api/images/card-back").status_code == 404
        assert c.get("/api/symbols").json() == {"symbols": {}}
        assert not c.app.state.services.linked.busy()
    assert calls == []
