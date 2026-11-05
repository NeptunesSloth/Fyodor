"""-- offline token art -- The Windows installer can carry every token's picture (seed/images, the image cache's layout). The server reads
them in place when its own cache has none, so a computer that never went online still shows token art (docs/OFFLINE.md)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config
from app.cards.images import ImageStore
from app.config import Settings, load_settings
from app.main import create_app
from tests.fixtures.cards import GOBLIN


def jpeg(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def test_the_store_falls_back_to_the_bundled_pictures(tmp_path: Path):
    cache, seed = tmp_path / "cache", tmp_path / "seed" / "images"
    gid = GOBLIN["id"]
    jpeg(ImageStore(seed).path_for(gid, is_token=True), b"bundled")
    store = ImageStore(cache, seed)
    assert store.find(gid) == ImageStore(seed).path_for(gid, is_token=True)
    assert ImageStore(cache).find(gid) is None  # without the bundle: nothing
    jpeg(store.path_for(gid, is_token=True), b"cached")  # the player's own cache wins (a newer download)
    assert store.find(gid) == store.path_for(gid, is_token=True)
    jpeg(ImageStore(seed).path_for(gid, size="small", is_token=True), b"small")
    assert ImageStore(cache, seed).find(gid, size="large") is not None  # other sizes, as for the cache


@pytest.fixture()
def offline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, Path]]:
    install = tmp_path / "install"
    monkeypatch.setattr(config, "install_dir", lambda: install)
    settings: Settings = load_settings({"FYODOR_DATA_DIR": str(tmp_path / "data"), "FYODOR_FRONTEND_DIST": str(tmp_path / "nodist"),
                                        "FYODOR_ALLOW_NETWORK": "0"})
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database(fixture_cards(), settings.cards_db_path, meta={"bulk_type": "test"})
    jpeg(ImageStore(install / "seed" / "images").path_for(GOBLIN["id"], is_token=True), b"\xff\xd8goblin")
    with TestClient(create_app(settings)) as c:
        yield c, install


def test_offline_the_server_serves_the_installers_token_art(offline):
    client, _ = offline
    res = client.get(f"/api/images/{GOBLIN['id']}")
    assert res.status_code == 200 and res.content == b"\xff\xd8goblin"
    card = client.get("/api/cards/search", params={"q": "goblin", "tokens": "true"}).json()["results"][0]
    assert card["has_image"] is True  # the table asks for the picture instead of drawing a frame
