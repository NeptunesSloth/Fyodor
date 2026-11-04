"""The Bag of Extras shows real token cards: the printing for each common token (POST /api/cards/tokens/find), and a token's
picture linked from Scryfall and cached the first time a client asks for it (GET /api/images/{id}, app/cards/token_art.py)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.config import Settings
from app.main import create_app
from tests.fixtures.cards import card, fixture_cards

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
DIGITAL = treasure("T3", released="2025-06-01", digital=True)
NO_PICTURE = treasure("T4", released="2025-03-01", image_uris=None)
OTHER_TEXT = treasure("T5", released="2025-08-01", oracle_text="{T}, Sacrifice this artifact: Add one mana of any color.",
                      oracle_id="00000000-0000-4000-8000-0000000000f5")
CROSSOVER = treasure("T6", released="2026-01-01", promo_types=["universesbeyond"])  # newer, but not the token's default
SOLDIER = token("Soldier", "S1", type_line="Token Creature — Soldier", power="1", toughness="1", colors=["W"], color_identity=["W"])
RED_SOLDIER = token("Soldier", "S2", released="2025-01-01", type_line="Token Creature — Soldier", power="1", toughness="1",
                    colors=["R"], color_identity=["R"])
ELSEWHERE = token("Spirit", "P1", type_line="Token Creature — Spirit", power="1", toughness="1", colors=["W"], oracle_text="Flying",
                  image_uris={"normal": "https://evil.example/spirit.jpg"})
TOKENS = [OLD, NEW, DIGITAL, NO_PICTURE, OTHER_TEXT, CROSSOVER, SOLDIER, RED_SOLDIER, ELSEWHERE]

TREASURE_SPEC = {"name": "Treasure", "type_line": "Token Artifact — Treasure", "text": TEXT, "colors": []}
SOLDIER_SPEC = {"name": "Soldier", "type_line": "Token Creature — Soldier", "power": "1", "toughness": "1", "colors": ["W"]}


@pytest.fixture()
def token_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *TOKENS], settings.cards_db_path,
                   meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.fixture()
def repo(settings: Settings, token_db: Path) -> Iterator[CardRepository]:
    r = CardRepository(token_db, ImageStore(settings.images_dir))
    yield r
    r.close()


@pytest.fixture()
def app_client(settings: Settings, token_db: Path) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as c:
        yield c


def test_the_tokens_default_printing_is_shown(repo: CardRepository) -> None:
    found = repo.find_token(TREASURE_SPEC)
    # the importer's default: not the digital one, the one without a picture, other rules text, nor a newer crossover printing
    assert found is not None and found["id"] == NEW["id"]
    assert found["is_token"] and found["has_image"] is False
    soldier = repo.find_token(SOLDIER_SPEC)
    assert soldier is not None and soldier["id"] == SOLDIER["id"]  # the white one: colours count
    assert repo.find_token({**SOLDIER_SPEC, "power": "2", "toughness": "2"}) is None
    assert repo.find_token({"name": "Treasure", "type_line": "Token Artifact — Treasure", "text": "Something else."}) is None


def test_a_printing_whose_picture_is_cached_comes_first(repo: CardRepository, settings: Settings) -> None:
    path = repo.images.path_for(OLD["id"], is_token=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(JPEG)
    found = repo.find_token(TREASURE_SPEC)
    assert found is not None and found["id"] == OLD["id"] and found["has_image"] is True


def test_the_bag_asks_for_its_tokens_in_one_request(app_client: TestClient) -> None:
    res = app_client.post("/api/cards/tokens/find", json={"tokens": [TREASURE_SPEC, SOLDIER_SPEC,
                                                                      {"name": "Blood", "type_line": "Token Artifact — Blood"}]})
    assert res.status_code == 200
    got = res.json()
    assert [c and c["id"] for c in got] == [NEW["id"], SOLDIER["id"], None]
    assert app_client.post("/api/cards/tokens/find", json={"tokens": []}).status_code == 422
    assert app_client.post("/api/cards/tokens/find", json={"tokens": [TREASURE_SPEC] * 25}).status_code == 422


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
