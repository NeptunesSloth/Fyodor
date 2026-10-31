"""UPDATE CARD DATABASE from Settings: check Scryfall, download, swap in, while tables keep reading cards."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.cards.importer import build_database, write_jsonl_gz
from tests.fixtures.cards import card, fixture_cards

BULK_URL = "https://data.scryfall.test/default-cards.jsonl.gz"
UPDATED_AT = "2026-10-31T09:04:12.123+00:00"
NEW_CARD = "Tester of New Sets"


@pytest.fixture()
def fake_scryfall(client, tmp_path: Path) -> dict[str, Any]:
    """Scryfall's bulk-data list and file, served from memory: the fixture cards plus one card from a "new set"."""
    bulk = tmp_path / "bulk.jsonl.gz"
    write_jsonl_gz([*fixture_cards(), card(NEW_CARD, set_code="new", number="7", type_line="Creature — Human",
                                           mana_cost="{1}{W}", cmc=2.0, oracle_text="Vigilance", power="2", toughness="2")], bulk)
    seen: dict[str, Any] = {"requests": [], "updated_at": UPDATED_AT}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["requests"].append(str(request.url))
        if request.url.path.endswith("/bulk-data"):
            return httpx.Response(200, json={"data": [{"type": "default_cards", "updated_at": seen["updated_at"],
                                                       "download_uri": BULK_URL, "size": bulk.stat().st_size}]})
        if str(request.url) == BULK_URL:
            return httpx.Response(200, content=bulk.read_bytes())
        return httpx.Response(404)

    client.app.state.services.http_client = lambda user_agent, timeout=60.0: httpx.Client(
        transport=httpx.MockTransport(handler), follow_redirects=True)
    return seen


def _wait(client) -> dict[str, Any]:
    deadline = time.time() + 30
    while time.time() < deadline:
        job = client.get("/api/card-data").json()["job"]
        if job and job["state"] != "running":
            return job
        time.sleep(0.05)
    raise AssertionError("the card update did not finish")


def test_check_download_and_switch_while_the_table_keeps_reading(client, fake_scryfall):
    before = client.get("/api/card-data").json()
    assert before["current"]["bulk_type"] == "test" and before["job"] is None and before["network"] is True
    assert client.get("/api/cards/search", params={"q": NEW_CARD}).json()["results"] == []

    found = client.post("/api/card-data/check").json()
    assert found["available"] is True and found["remote_updated_at"] == UPDATED_AT and found["bulk_type"] == "default_cards"

    started = client.post("/api/card-data/update")
    assert started.status_code == 202 and started.json()["kind"] == "card-update"
    job = _wait(client)
    assert job["state"] == "done", job["message"]
    assert job["message"].startswith("Updated: ") and "(1 new card)" in job["message"]
    assert job["phase"] == "Switching over"

    after = client.get("/api/card-data").json()["current"]
    assert after["bulk_type"] == "default_cards" and after["bulk_updated_at"] == UPDATED_AT
    names = [c["name"] for c in client.get("/api/cards/search", params={"q": NEW_CARD}).json()["results"]]
    assert names == [NEW_CARD]  # the live repository reopened the new file
    assert client.post("/api/card-data/check").json()["available"] is False

    # nothing new: the second press says so without downloading again
    downloads = sum(r == BULK_URL for r in fake_scryfall["requests"])
    client.post("/api/card-data/update")
    assert "already current" in _wait(client)["message"]
    assert sum(r == BULK_URL for r in fake_scryfall["requests"]) == downloads


def test_card_updates_are_host_only_and_respect_offline_mode(client, fake_scryfall):
    remote = {"X-Forwarded-For": "192.168.1.50"}
    assert client.get("/api/card-data", headers=remote).status_code == 403
    assert client.post("/api/card-data/check", headers=remote).status_code == 403
    assert client.post("/api/card-data/update", headers=remote).status_code == 403
    services = client.app.state.services
    object.__setattr__(services.settings, "allow_network", False)
    try:
        assert client.post("/api/card-data/check").status_code == 409
        assert client.post("/api/card-data/update").status_code == 409
        assert client.get("/api/card-data").json()["network"] is False
    finally:
        object.__setattr__(services.settings, "allow_network", True)
    assert fake_scryfall["requests"] == []


def test_scryfall_unreachable_is_a_clear_error(client):
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host", request=request)

    client.app.state.services.http_client = lambda user_agent, timeout=60.0: httpx.Client(transport=httpx.MockTransport(down))
    res = client.post("/api/card-data/check")
    assert res.status_code == 502 and "Couldn't reach Scryfall" in res.json()["detail"]
    client.post("/api/card-data/update")
    job = _wait(client)
    assert job["state"] == "failed" and "no route to host" in job["message"]
    assert client.get("/api/card-data").json()["current"]["bulk_type"] == "test"  # the old data is untouched


def test_replace_with_swaps_an_open_database(cards, tmp_path: Path):
    assert cards.search("Sol Ring")  # the connection is open
    fresh = tmp_path / "fresh.sqlite"
    build_database([card(NEW_CARD, set_code="new", number="7")], fresh, meta={"bulk_type": "default_cards"})
    cards.replace_with(fresh)
    assert not fresh.exists()
    assert [c["name"] for c in cards.search(NEW_CARD)] == [NEW_CARD] and not cards.search("Sol Ring")
