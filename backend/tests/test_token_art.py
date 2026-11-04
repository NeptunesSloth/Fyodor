"""The Bag of Extras shows the deck's own tokens as their printed cards: the tokens a deck makes, found when its game starts, and
a token's picture linked from Scryfall and cached the first time a client asks for it (GET /api/images/{id}, app/cards/token_art.py)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.cards.importer import build_database
from app.config import Settings
from app.main import create_app
from tests.fixtures.cards import GOBLIN, card, fixture_cards

TEXT = "{T}, Sacrifice this token: Add one mana of any color."
JPEG = b"\xff\xd8\xff\xe0token"


def token(name: str, number: str, *, released: str = "2020-01-01", **extra: Any) -> dict[str, Any]:
    extra.setdefault("image_uris", {"normal": f"https://cards.scryfall.io/normal/front/{number}.jpg",
                                    "small": f"https://cards.scryfall.io/small/front/{number}.jpg"})
    return card(name, set_code="tok", number=number, layout="token", set_type="token", released_at=released, **extra)


def treasure(number: str, **extra: Any) -> dict[str, Any]:
    return token("Treasure", number, type_line="Token Artifact — Treasure", **{"oracle_text": TEXT, **extra})


OLD = treasure("T1", released="2018-01-19")
NEW = treasure("T2", released="2024-11-15")
NO_PICTURE = treasure("T4", released="2025-03-01", image_uris=None)
SOLDIER = token("Soldier", "S1", type_line="Token Creature — Soldier", power="1", toughness="1", colors=["W"], color_identity=["W"])
ELSEWHERE = token("Spirit", "P1", type_line="Token Creature — Spirit", power="1", toughness="1", colors=["W"], oracle_text="Flying",
                  image_uris={"normal": "https://evil.example/spirit.jpg"})
MAKER = card("Test Treasure Maker", number="TM1", type_line="Creature — Human", oracle_text="When this creature enters, create a Treasure token.",
             power="1", toughness="1", all_parts=[{"object": "related_card", "id": NEW["id"], "component": "token", "name": "Treasure",
                                                   "type_line": "Token Artifact — Treasure"}])
TOKENS = [OLD, NEW, NO_PICTURE, SOLDIER, ELSEWHERE, MAKER]


@pytest.fixture()
def token_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *TOKENS], settings.cards_db_path,
                   meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.fixture()
def app_client(settings: Settings, token_db: Path) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as c:
        yield c


def test_a_deck_brings_the_tokens_its_cards_make(app_client: TestClient) -> None:
    """The Bag of Extras lists only the deck's tokens: its Tokens section and the tokens its cards make (Scryfall's related
    tokens), found when the game starts and seen by the deck's owner only."""
    text = "Commander\n1 Krenko, Mob Boss\nDeck\n1 Test Treasure Maker\n1 Sol Ring\nTokens\n1 Soldier (tok) S1\n"
    alice = app_client.post("/api/decks", json={"name": "Goblins", "text": text}).json()["id"]
    bob = app_client.post("/api/decks", json={"name": "Rings", "text": "1 Sol Ring\n"}).json()["id"]
    game = app_client.post("/api/games", json={"name": "Bag", "mode": "local", "players": [
        {"name": "Alice", "deck_id": alice}, {"name": "Bob", "deck_id": bob}]}).json()["game"]["id"]

    def bag(viewer: str, seat: str) -> Any:
        view = app_client.get(f"/api/games/{game}/view?viewer={viewer}").json()
        return next(p for p in view["players"] if p["id"] == seat).get("token_shortcuts")

    assert bag("p1", "p1") == [SOLDIER["id"], GOBLIN["id"], NEW["id"]]  # the Tokens section first, then what the cards make
    assert bag("p2", "p2") == []  # Sol Ring makes none
    assert bag("p2", "p1") is None  # never another player's


# -- the picture, linked from Scryfall when first asked for -------------------------------------------------------------


@pytest.fixture()
def scryfall(app_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.setattr("app.cards.token_art.DOWNLOADS", True)
    seen: dict[str, Any] = {"calls": [], "down": False}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["calls"].append(str(request.url))
        if seen["down"]:
            raise httpx.ConnectError("no internet")
        return httpx.Response(200, content=JPEG, headers={"Content-Type": "image/jpeg"})

    services = app_client.app.state.services
    services.http_client = lambda user_agent, timeout=60.0: httpx.Client(transport=httpx.MockTransport(handler))
    return seen


def test_a_token_picture_is_fetched_once_and_cached(app_client: TestClient, scryfall: dict[str, Any]) -> None:
    res = app_client.get(f"/api/images/{NEW['id']}?size=small")
    assert res.status_code == 200 and res.content == JPEG
    assert scryfall["calls"] == ["https://cards.scryfall.io/normal/front/T2.jpg"]
    assert app_client.get(f"/api/images/{NEW['id']}").status_code == 200
    assert len(scryfall["calls"]) == 1  # cached: never asked again
    assert app_client.post("/api/cards/batch", json={"ids": [NEW["id"]]}).json()[NEW["id"]]["has_image"] is True


def test_only_tokens_and_only_from_scryfall(app_client: TestClient, scryfall: dict[str, Any]) -> None:
    sol_ring = next(c for c in fixture_cards() if c["name"] == "Sol Ring")
    assert app_client.get(f"/api/images/{sol_ring['id']}").status_code == 404  # a deck's own cards come with the deck
    assert app_client.get(f"/api/images/{ELSEWHERE['id']}").status_code == 404  # a picture somewhere else is never fetched
    assert app_client.get(f"/api/images/{NO_PICTURE['id']}").status_code == 404
    assert scryfall["calls"] == []


def test_offline_it_is_a_404_and_not_asked_again_at_once(app_client: TestClient, scryfall: dict[str, Any]) -> None:
    scryfall["down"] = True
    assert app_client.get(f"/api/images/{OLD['id']}").status_code == 404
    assert app_client.get(f"/api/images/{OLD['id']}").status_code == 404
    assert len(scryfall["calls"]) == 1  # (tried again after RETRY_SECONDS)


def test_never_with_the_network_turned_off(app_client: TestClient, scryfall: dict[str, Any]) -> None:
    services = app_client.app.state.services
    object.__setattr__(services.settings, "allow_network", False)
    try:
        assert app_client.get(f"/api/images/{NEW['id']}").status_code == 404
    finally:
        object.__setattr__(services.settings, "allow_network", True)
    assert scryfall["calls"] == []
