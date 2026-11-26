"""-- art folders -- more folders of card pictures, read in place after the cache: the host adds one in Settings → Card database
(any of a few layouts), Fyodor finds %USERPROFILE%\\Fyodor\\images on its own, and FYODOR_ART_DIRS names more (docs/OFFLINE.md)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config
from app.cards import art_fallback, art_folders
from app.cards.images import ImageStore
from app.config import Settings, load_settings
from app.main import create_app
from tests.conftest import claim_host, guest
from tests.fixtures.cards import GOBLIN, fixture_cards

GID = GOBLIN["id"]
PNG = b"\x89PNG\r\n\x1a\n" + b"png"


def write(path: Path, body: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path


def a_card_id() -> str:
    return next(c["id"] for c in fixture_cards() if c.get("layout") != "token")


@pytest.fixture(autouse=True)
def _no_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(art_fallback, "TTL_SECONDS", 0.0)


def make_settings(tmp_path: Path, **env: str) -> Settings:
    return load_settings({"FYODOR_DATA_DIR": str(tmp_path / "data"), "FYODOR_FRONTEND_DIST": str(tmp_path / "nodist"),
                          "FYODOR_ALLOW_NETWORK": "0", **env})


@pytest.fixture()
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, Settings]]:
    monkeypatch.setattr(config, "install_dir", lambda: tmp_path / "install")
    settings = make_settings(tmp_path)
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database(fixture_cards(), settings.cards_db_path, meta={"bulk_type": "test"})
    with TestClient(create_app(settings)) as c:
        claim_host(c)
        yield c, settings


def folders(client: TestClient) -> list[dict]:
    res = client.get("/api/art-folders")
    assert res.status_code == 200
    return res.json()["folders"]


def test_an_added_folder_in_fyodors_layout_is_read_in_place(server, tmp_path):
    client, settings = server
    other = tmp_path / "usb" / "images"
    pic = write(ImageStore(other).path_for(GID, is_token=True), b"\xff\xd8usb")
    assert client.get(f"/api/images/{GID}").status_code == 404
    res = client.post("/api/art-folders", json={"path": f'"{other}"'})  # (pasted with quotes, as Explorer copies it)
    assert res.status_code == 200, res.text
    assert res.json()["added"] | {"path": str(other.resolve())} == {
        "path": str(other.resolve()), "folder": str(other.resolve()), "source": "added", "exists": True, "layout": "fyodor", "count": 1}
    got = client.get(f"/api/images/{GID}")
    assert got.status_code == 200 and got.content == b"\xff\xd8usb" and got.headers["content-type"] == "image/jpeg"
    assert pic.read_bytes() == b"\xff\xd8usb" and not ImageStore(settings.images_dir).path_for(GID, is_token=True).exists()  # never copied
    saved = json.loads((settings.data_dir / "art-folders.json").read_text(encoding="utf-8"))
    assert saved == {"folders": [str(other.resolve())]}
    card = client.get("/api/cards/search", params={"q": "goblin", "tokens": "true"}).json()["results"][0]
    assert card["has_image"] is True


def test_a_folder_holding_an_images_folder_is_descended_into(server, tmp_path):
    client, _ = server
    home = tmp_path / "other-pc" / "Fyodor"
    write(ImageStore(home / "data" / "images").path_for(GID), b"\xff\xd8data")
    res = client.post("/api/art-folders", json={"path": str(home)})
    assert res.status_code == 200, res.text
    assert res.json()["added"]["folder"] == str((home / "data" / "images").resolve())
    assert client.get(f"/api/images/{GID}").content == b"\xff\xd8data"
    install = tmp_path / "install-copy"
    write(ImageStore(install / "seed" / "images").path_for(a_card_id()), b"\xff\xd8seed")
    assert client.post("/api/art-folders", json={"path": str(install)}).status_code == 200
    assert client.get(f"/api/images/{a_card_id()}").content == b"\xff\xd8seed"


def test_loose_pictures_named_by_id_are_indexed(server, tmp_path):
    client, _ = server
    loose = tmp_path / "scans"
    cid = a_card_id()
    write(loose / "sets" / "tst" / f"{GID}.jpg", b"\xff\xd8bare")  # two folders down, by id alone
    write(loose / f"{cid}-0-large.png", PNG)
    write(loose / "notes.txt", b"hello")
    res = client.post("/api/art-folders", json={"path": str(loose)})
    assert res.status_code == 200, res.text
    assert res.json()["added"]["layout"] == "loose" and res.json()["added"]["count"] == 2
    assert client.get(f"/api/images/{GID}", params={"size": "small"}).content == b"\xff\xd8bare"
    assert client.get(f"/api/images/{GID}", params={"size": "art_crop"}).status_code == 404  # a whole card isn't an art crop
    got = client.get(f"/api/images/{cid}", params={"fallback": 0})
    assert got.status_code == 200 and got.headers["content-type"] == "image/png"
    # a picture copied in later shows after a rescan
    other = next(c["id"] for c in fixture_cards() if c["id"] not in (cid, GID) and c.get("layout") != "token")
    write(loose / f"{other}-0-normal.jpg", b"\xff\xd8later")
    assert client.get(f"/api/images/{other}", params={"fallback": 0}).status_code == 404
    rescanned = client.post("/api/art-folders/rescan").json()["folders"]
    assert [f["count"] for f in rescanned if f["source"] == "added"] == [3]
    assert client.get(f"/api/images/{other}", params={"fallback": 0}).content == b"\xff\xd8later"


def test_the_cache_wins_over_the_folders(server, tmp_path):
    client, settings = server
    other = tmp_path / "pack"
    write(ImageStore(other).path_for(GID, is_token=True), b"\xff\xd8pack")
    assert client.post("/api/art-folders", json={"path": str(other)}).status_code == 200
    write(ImageStore(settings.images_dir).path_for(GID, is_token=True), b"\xff\xd8cache")
    assert client.get(f"/api/images/{GID}").content == b"\xff\xd8cache"


def test_removing_a_folder(server, tmp_path):
    client, settings = server
    other = tmp_path / "pack"
    write(ImageStore(other).path_for(GID, is_token=True), b"\xff\xd8pack")
    assert client.post("/api/art-folders", json={"path": str(other)}).status_code == 200
    assert client.get(f"/api/images/{GID}").status_code == 200
    res = client.delete("/api/art-folders", params={"path": str(other)})
    assert res.status_code == 200 and res.json()["folders"] == []
    assert client.get(f"/api/images/{GID}").status_code == 404
    assert other.is_dir() and json.loads((settings.data_dir / "art-folders.json").read_text(encoding="utf-8")) == {"folders": []}
    assert client.delete("/api/art-folders", params={"path": str(other)}).status_code == 400


def test_bad_folders_are_refused(server, tmp_path):
    client, settings = server
    res = client.post("/api/art-folders", json={"path": str(tmp_path / "nope")})
    assert res.status_code == 400 and "no folder" in res.json()["detail"]
    (tmp_path / "empty" / "sub").mkdir(parents=True)
    write(tmp_path / "empty" / "cat.jpg", b"\xff\xd8")
    res = client.post("/api/art-folders", json={"path": str(tmp_path / "empty")})
    assert res.status_code == 400 and "No card pictures" in res.json()["detail"] and "Scryfall id" in res.json()["detail"]
    assert client.post("/api/art-folders", json={"path": "relative\\images"}).status_code == 400
    write(ImageStore(settings.images_dir).path_for(GID), b"\xff\xd8")
    assert "own picture cache" in client.post("/api/art-folders", json={"path": str(settings.images_dir)}).json()["detail"]
    assert folders(client) == []


def test_only_the_host_manages_folders(server):
    client, _ = server
    remote = guest()
    assert client.get("/api/art-folders", headers=remote).status_code == 403
    assert client.post("/api/art-folders", json={"path": "C:\\x"}, headers=remote).status_code == 403


def test_request_ids_are_still_validated(server, tmp_path):
    client, _ = server
    loose = tmp_path / "scans"
    write(loose / f"{GID}.jpg", b"\xff\xd8")
    assert client.post("/api/art-folders", json={"path": str(loose)}).status_code == 200
    assert client.get("/api/images/..%2F..%2Fsecret").status_code in (400, 404)
    assert client.get(f"/api/images/{GID.upper()}").status_code == 400
    assert client.get("/api/images/not-a-uuid").status_code == 400


def test_fyodor_images_in_the_home_folder_are_found_on_their_own(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr(art_folders, "home_dir", lambda: home)
    monkeypatch.setattr(config, "install_dir", lambda: tmp_path / "install")
    write(ImageStore(home / "Fyodor" / "images").path_for(GID, is_token=True), b"\xff\xd8home")
    settings = make_settings(tmp_path)
    settings.ensure_dirs()
    store = ImageStore(settings.images_dir)
    found = art_folders.ArtFolders(settings, store)
    assert [(f["source"], f["count"]) for f in found.listing()] == [("auto", 1)]
    assert store.find(GID) == ImageStore(home / "Fyodor" / "images").path_for(GID, is_token=True)
    # the cache itself is never an art folder (the installed app's data folder is %USERPROFILE%\Fyodor\data)
    settings = make_settings(tmp_path, FYODOR_DATA_DIR=str(home / "Fyodor" / "data"))
    settings.ensure_dirs()
    assert [f["folder"] for f in art_folders.ArtFolders(settings, ImageStore(settings.images_dir)).listing()] == [
        str(home / "Fyodor" / "images")]


def test_folders_named_in_the_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "install_dir", lambda: tmp_path / "install")
    one, two = tmp_path / "one", tmp_path / "two"
    write(ImageStore(two).path_for(GID), b"\xff\xd8two")
    import os

    settings = make_settings(tmp_path, FYODOR_ART_DIRS=os.pathsep.join([str(one), str(two)]))
    settings.ensure_dirs()
    store = ImageStore(settings.images_dir)
    listing = art_folders.ArtFolders(settings, store).listing()
    assert {(f["path"], f["source"], f["exists"]) for f in listing} == {(str(two), "env", True), (str(one), "env", False)}
    assert store.find(GID) is not None
