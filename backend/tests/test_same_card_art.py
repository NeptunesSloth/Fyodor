"""-- same-card art -- a printing with no picture on this computer shows another printing's picture of the same card (an art pack
in seed/images holds one printing of each card; a deck may ask for another)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app import config
from app.cards import art_fallback
from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.config import Settings, load_settings
from app.main import create_app
from app.multiplayer import lan_art
from tests.conftest import claim_host
from tests.fixtures.cards import card


def dfc(layout: str, set_code: str, number: str, released: str) -> dict[str, Any]:
    return card("Delver of Secrets // Insectile Aberration", set_code=set_code, number=number, layout=layout, released_at=released,
                image_uris=None, card_faces=[
                    {"object": "card_face", "name": "Delver of Secrets", "type_line": "Creature", "image_uris": {"normal": "https://x/f.jpg"}},
                    {"object": "card_face", "name": "Insectile Aberration", "type_line": "Creature", "image_uris": {"normal": "https://x/b.jpg"}},
                ])


SOL_DEFAULT = card("Sol Ring", set_code="cmm", number="410", released_at="2023-08-04")
SOL_OLD = card("Sol Ring", set_code="c21", number="263", released_at="2021-04-23")
SOL_PROMO = card("Sol Ring", set_code="sld", number="999", released_at="2024-01-01", set_type="box", promo=True)
DELVER = dfc("transform", "isd", "51", "2011-09-30")
DELVER_2 = dfc("transform", "inr", "60", "2024-01-01")
DELVER_MDFC = dfc("modal_dfc", "xxx", "1", "2025-01-01")  # (made up: another layout with two faces)
GOBLIN_1 = card("Goblin", set_code="ttst", number="T2", layout="token", set_type="token", type_line="Token Creature — Goblin")
GOBLIN_2 = card("Goblin", set_code="tzzz", number="T9", layout="token", set_type="token", type_line="Token Creature — Goblin",
                released_at="2010-01-01")
CARDS = [SOL_DEFAULT, SOL_OLD, SOL_PROMO, DELVER, DELVER_2, DELVER_MDFC, GOBLIN_1, GOBLIN_2]


def jpeg(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


@pytest.fixture(autouse=True)
def _no_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(art_fallback, "TTL_SECONDS", 0.0)  # every request scans again: files change between steps here


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, ImageStore, ImageStore]]:
    install = tmp_path / "install"
    monkeypatch.setattr(config, "install_dir", lambda: install)
    settings: Settings = load_settings({"FYODOR_DATA_DIR": str(tmp_path / "data"), "FYODOR_FRONTEND_DIST": str(tmp_path / "nodist"),
                                        "FYODOR_ALLOW_NETWORK": "0"})
    settings.ensure_dirs()
    build_database(CARDS, settings.cards_db_path, meta={"bulk_type": "test"})
    (install / "seed" / "images").mkdir(parents=True)  # the art pack beside Fyodor.exe
    with TestClient(create_app(settings)) as c:
        claim_host(c)
        yield c, ImageStore(settings.images_dir), ImageStore(install / "seed" / "images")


def default_of(client: TestClient, name: str) -> str:
    return client.get("/api/cards/search", params={"q": name, "tokens": "any"}).json()["results"][0]["id"]


def test_the_exact_printing_wins_then_the_default_printings_art(env):
    client, cache, _ = env
    assert default_of(client, "sol ring") == SOL_DEFAULT["id"]
    assert client.get(f"/api/images/{SOL_OLD['id']}").status_code == 404  # no art of the card anywhere: a proxy
    jpeg(cache.path_for(SOL_DEFAULT["id"]), b"\xff\xd8default")
    jpeg(cache.path_for(SOL_PROMO["id"]), b"\xff\xd8promo")
    res = client.get(f"/api/images/{SOL_OLD['id']}")
    assert res.status_code == 200 and res.content == b"\xff\xd8default"  # the default printing's, before the newest
    assert res.headers["cache-control"] == "no-cache" and res.headers["x-fyodor-art"] == "another-printing"
    assert client.get(f"/api/images/{SOL_OLD['id']}", params={"fallback": 0}).status_code == 404
    jpeg(cache.path_for(SOL_OLD["id"]), b"\xff\xd8old")
    res = client.get(f"/api/images/{SOL_OLD['id']}")
    assert res.content == b"\xff\xd8old" and "max-age" in res.headers["cache-control"] and "x-fyodor-art" not in res.headers
    assert client.get(f"/api/images/{SOL_DEFAULT['id']}").content == b"\xff\xd8default"


def test_any_printing_with_art_when_the_default_has_none_and_the_art_pack_is_read_in_place(env):
    client, _, pack = env
    jpeg(pack.path_for(SOL_PROMO["id"], size="small"), b"\xff\xd8pack")  # the art pack: small pictures only
    for size in ("normal", "small", "large"):
        res = client.get(f"/api/images/{SOL_OLD['id']}", params={"size": size})
        assert res.status_code == 200 and res.content == b"\xff\xd8pack"
    assert client.get(f"/api/images/{SOL_OLD['id']}", params={"size": "art_crop"}).status_code == 404
    jpeg(pack.path_for(SOL_PROMO["id"], size="art_crop"), b"\xff\xd8crop")
    assert client.get(f"/api/images/{SOL_OLD['id']}", params={"size": "art_crop"}).content == b"\xff\xd8crop"


def test_has_image_counts_borrowed_art_and_own_image_does_not(env):
    client, cache, _ = env
    jpeg(cache.path_for(SOL_DEFAULT["id"]), b"\xff\xd8default")
    printings = {p["id"]: p for p in client.get(f"/api/cards/{SOL_OLD['id']}/printings").json()}
    assert printings[SOL_DEFAULT["id"]]["own_image"] is True and printings[SOL_DEFAULT["id"]]["has_image"] is True
    assert printings[SOL_OLD["id"]]["own_image"] is False and printings[SOL_OLD["id"]]["has_image"] is True
    assert printings[SOL_OLD["id"]]["art_from"] == SOL_DEFAULT["id"] and "art_from" not in printings[SOL_DEFAULT["id"]]
    assert client.get(f"/api/cards/{DELVER['id']}").json()["has_image"] is False


def test_a_back_face_borrows_only_from_the_same_layout(env):
    client, cache, _ = env
    jpeg(cache.path_for(DELVER_MDFC["id"], face=0), b"\xff\xd8mdfc-front")
    jpeg(cache.path_for(DELVER_MDFC["id"], face=1), b"\xff\xd8mdfc-back")
    assert client.get(f"/api/images/{DELVER['id']}", params={"face": 0}).content == b"\xff\xd8mdfc-front"  # a front is a front
    assert client.get(f"/api/images/{DELVER['id']}", params={"face": 1}).status_code == 404  # another layout's back: no
    jpeg(cache.path_for(DELVER_2["id"], face=1), b"\xff\xd8inr-back")
    assert client.get(f"/api/images/{DELVER['id']}", params={"face": 1}).content == b"\xff\xd8inr-back"
    assert client.get(f"/api/images/{SOL_OLD['id']}", params={"face": 1}).status_code == 404


def test_tokens_still_fetch_their_own_art_first(env, monkeypatch):
    client, cache, _ = env
    services = client.app.state.services
    asked: list[tuple[str, int]] = []
    monkeypatch.setattr(services.token_art, "fetch", lambda cid, face=0: asked.append((cid, face)))
    jpeg(cache.path_for(GOBLIN_2["id"], is_token=True), b"\xff\xd8other-goblin")
    res = client.get(f"/api/images/{GOBLIN_1['id']}")
    assert asked == [(GOBLIN_1["id"], 0)]  # the token's own picture is asked for (online), then another printing's stands in
    assert res.status_code == 200 and res.content == b"\xff\xd8other-goblin"


def test_bad_ids_are_still_refused(env):
    client, _, _ = env
    assert client.get("/api/images/not-a-uuid").status_code == 400
    assert client.get("/api/images/00000000-0000-0000-0000-000000000000").status_code == 404  # unknown printing: no family


def test_deck_art_status_counts_borrowed_art(env):
    client, cache, _ = env
    deck = client.post("/api/decks", json={"name": "Rings"}).json()
    client.put(f"/api/decks/{deck['id']}", json={"name": "Rings", "entries": [
        {"name": "Sol Ring", "quantity": 1, "printing_id": SOL_OLD["id"]},
        {"name": "Delver of Secrets // Insectile Aberration", "quantity": 1, "printing_id": DELVER["id"]},
    ]}).raise_for_status()
    assert client.get(f"/api/decks/{deck['id']}/art-status").json() == {"printings": 2, "missing": 2, "borrowed": 0}
    jpeg(cache.path_for(SOL_DEFAULT["id"]), b"\xff\xd8default")
    assert client.get(f"/api/decks/{deck['id']}/art-status").json() == {"printings": 2, "missing": 2, "borrowed": 1}


def test_the_lan_art_fetch_never_keeps_another_printings_art(tmp_path):
    store = ImageStore(tmp_path / "images")
    seen: list[httpx.QueryParams] = []

    class Repo:
        def get_many(self, ids: list[str]) -> dict[str, Any]:
            return {i: {"image_faces": 1, "is_token": False} for i in ids}

    def peer(borrowed: bool) -> httpx.MockTransport:
        def handle(req: httpx.Request) -> httpx.Response:
            seen.append(req.url.params)
            headers = {"content-type": "image/jpeg", **({"x-fyodor-art": "another-printing"} if borrowed else {})}
            return httpx.Response(200, content=b"\xff\xd8" + b"x" * 100, headers=headers)
        return httpx.MockTransport(handle)

    pid = SOL_OLD["id"]
    assert lan_art.fetch_art("http://192.168.1.20:8000", Repo(), store, [pid], transport=peer(True)) == []  # type: ignore[arg-type]
    assert not store.path_for(pid).exists() and seen[-1]["fallback"] == "0"
    assert lan_art.fetch_art("http://192.168.1.20:8000", Repo(), store, [pid], transport=peer(False)) == [pid]  # type: ignore[arg-type]


def test_the_scan_stops_at_the_first_printings_with_art(env, monkeypatch):
    client, cache, _ = env
    jpeg(cache.path_for(SOL_DEFAULT["id"]), b"\xff\xd8default")
    jpeg(cache.path_for(SOL_PROMO["id"]), b"\xff\xd8promo")
    services = client.app.state.services
    probed: list[str] = []
    real = services.images.find
    monkeypatch.setattr(services.images, "find", lambda cid, **kw: probed.append(cid) or real(cid, **kw))
    assert client.get(f"/api/images/{SOL_OLD['id']}").content == b"\xff\xd8default"
    # its own picture, then the scan: the default has art, so no other printing is looked at (an art pack: the default only)
    assert probed == [SOL_OLD["id"], SOL_DEFAULT["id"], SOL_DEFAULT["id"]]
