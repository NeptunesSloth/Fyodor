"""``DeckSource.url`` is shown as a link in the deck editor: only an absolute http(s) address with a host may be stored there."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.decks.models import DeckSource

KRENKO = "Commander" + chr(10) + "1 Krenko, Mob Boss" + chr(10)
GOOD = ["https://archidekt.com/decks/123", "http://archidekt.com/decks/123", "HTTPS://Archidekt.com/decks/1?x=1#y", "http://192.168.1.2:8000/a",
        "http://[::1]:8000/"]
BAD = ["javascript:alert(1)", "JaVaScRiPt:alert(1)", "data:text/html,<b>x</b>", "file:///etc/passwd", "//evil.example/x", "/decks/1", "archidekt.com/decks/1",
       "ftp://archidekt.com/x", "https://", "https:///path", "http:", " https://archidekt.com/decks/1", "https://archidekt.com/decks/1 ",
       "https://archidekt.com/de cks", "https://arch\tidekt.com/", "https://archidekt.com/\x07", "https://archidekt.com/\n", "https://archidekt.com/\x7f",
       "http://host:notaport/", "https://[::1/"]


@pytest.mark.parametrize("url", GOOD)
def test_http_and_https_urls_are_kept(url):
    assert DeckSource(url=url).url == url


@pytest.mark.parametrize("url", BAD)
def test_anything_else_is_rejected_by_the_model(url):
    with pytest.raises(ValidationError, match="url"):
        DeckSource(url=url)


def test_empty_and_missing_urls_stay_allowed():
    assert DeckSource().url is None
    assert DeckSource(url=None).url is None
    assert DeckSource(url="").url == ""


def _store_source(client, source_json: str) -> str:
    services = client.app.state.services
    created = client.post("/api/decks", json={"text": KRENKO, "name": "D"})
    deck = services.decks.get(created.json()["id"])
    with services.decks.lock:
        services.decks.conn.execute("UPDATE decks SET source = ? WHERE id = ?", (source_json, deck.id))
        services.decks.conn.commit()
    return deck.id


@pytest.mark.parametrize("bad", ["javascript:alert(1)", "data:text/html,x", "//evil.example", "https://", "ftp://x.org/"])
def test_a_deck_stored_with_a_bad_url_still_loads_with_the_url_dropped(client, bad):
    """Saved before the check existed, or restored from a hand-made backup: the deck opens, the link is gone, the rest of the source stays."""
    deck_id = _store_source(client, DeckSource.model_construct(kind="archidekt", id="123", url=bad, name="Goblins").model_dump_json())
    res = client.get(f"/api/decks/{deck_id}")
    assert res.status_code == 200, res.text
    assert res.json()["source"]["url"] is None
    assert res.json()["source"]["name"] == "Goblins" and res.json()["source"]["id"] == "123"
    assert any(d["id"] == deck_id for d in client.get("/api/decks").json())


def test_a_deck_stored_with_a_good_url_keeps_it(client):
    deck_id = _store_source(client, DeckSource(kind="archidekt", id="123", url="https://archidekt.com/decks/123").model_dump_json())
    assert client.get(f"/api/decks/{deck_id}").json()["source"]["url"] == "https://archidekt.com/decks/123"
