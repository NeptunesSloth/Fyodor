from __future__ import annotations

from collections.abc import Iterator
import functools
import os
import sys
from pathlib import Path
from typing import Any

import pytest

# Windows: the locale code page (cp1252) is the default text encoding, and game states hold characters like "→" and "—". The
# app always names an encoding; many tests write/read saved states with bare ``Path.write_text``/``read_text`` and hand them to a
# fresh ``sys.executable`` process. Make both this process's bare Path text I/O and every child process speak UTF-8, as they do
# on Linux/macOS (and here under PYTHONUTF8=1), so the tests check the same thing on every platform.
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if not sys.flags.utf8_mode:
    _read_text, _write_text = Path.read_text, Path.write_text

    def _utf8_read_text(self, encoding=None, errors=None, *args, **kwargs):  # type: ignore[no-untyped-def]
        return _read_text(self, encoding or "utf-8", errors, *args, **kwargs)

    def _utf8_write_text(self, data, encoding=None, errors=None, *args, **kwargs):  # type: ignore[no-untyped-def]
        return _write_text(self, data, encoding or "utf-8", errors, *args, **kwargs)

    Path.read_text = _utf8_read_text  # type: ignore[method-assign]
    Path.write_text = _utf8_write_text  # type: ignore[method-assign]
from fastapi.testclient import TestClient

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.config import Settings, load_settings
from app.main import create_app
from tests.fixtures.cards import fixture_cards


@pytest.fixture(autouse=True)
def _fresh_printed_cache() -> None:
    # Printed characteristics are cached per printing id for the process. Real printings never change, but two test files may give
    # the same fixture id different data (wave 12A's "Test Giant" costs {6}, wave 16C's {5}; wave 110G's two "Test Doctor"s cost {G}
    # and {2}; all get ids like "Test Giant|tst|12A-Test Gi"). Many test files bring their own ``cards`` fixture, so every test starts
    # from an empty cache here: what a test sees never depends on which tests ran before it.
    from app.rules import characteristics

    characteristics._printed_cache.clear()
    characteristics._fused_cache.clear()


@pytest.fixture(autouse=True)
def _testserver_is_a_known_host(monkeypatch: pytest.MonkeyPatch) -> None:
    # the test client's Host is "testserver", a name the Host guard (app/netguard.py) refuses unless told (FYODOR_EXTRA_HOSTS). Every
    # test builds its settings through ``load_settings``, so tell it there, below the environment a test passes (which may say otherwise).
    from app import config

    real = config._load_dotenv
    monkeypatch.setattr(config, "_load_dotenv", lambda path: {"FYODOR_EXTRA_HOSTS": "testserver", **real(path)})


@pytest.fixture(autouse=True)
def _sockets_send_the_page_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    # a browser always sends an Origin when it opens a socket, and the server refuses a socket without an allowed one (app/netguard.py):
    # the test client sends the page's own unless the test names another. ``TestClient.websocket_connect.__wrapped__`` sends none.
    real = TestClient.websocket_connect

    @functools.wraps(real)
    def connect(self: TestClient, url: str, subprotocols: Any = None, **kwargs: Any) -> Any:
        headers = dict(kwargs.pop("headers", None) or {})
        if not any(k.lower() == "origin" for k in headers):
            headers["Origin"] = "http://testserver"
        return real(self, url, subprotocols, headers=headers, **kwargs)

    monkeypatch.setattr(TestClient, "websocket_connect", connect)


@pytest.fixture(autouse=True)
def _no_art_downloads(monkeypatch: pytest.MonkeyPatch) -> None:
    # -- keep deck art -- saving a deck downloads its art while online (app/cards/art_keeper.py); never in the tests unless one
    # turns it on for its own server (``services.art_keeper.downloads = True``)
    monkeypatch.setattr("app.cards.art_keeper.DOWNLOADS", False)
    # -- the card back and mana symbols -- fetched at start-up and on demand while online (app/cards/linked.py); likewise
    # never in the tests unless one turns it on (``app.cards.linked.DOWNLOADS``) with a mocked Scryfall
    monkeypatch.setattr("app.cards.linked.DOWNLOADS", False)
    # -- token pictures -- fetched when a client first asks for one (app/cards/token_art.py): likewise
    monkeypatch.setattr("app.cards.token_art.DOWNLOADS", False)


@pytest.fixture(autouse=True)
def _no_home_art_folders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # -- art folders -- the server reads %USERPROFILE%\Fyodor\images and the like when they exist (app/cards/art_folders.py):
    # never this computer's own in the tests, so what a test sees doesn't depend on whose machine it runs on
    monkeypatch.setattr("app.cards.art_folders.home_dir", lambda: tmp_path / "home")


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return load_settings({"FYODOR_DATA_DIR": str(tmp_path / "data"), "FYODOR_FRONTEND_DIST": str(tmp_path / "nodist")})


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database(fixture_cards(), settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.fixture()
def cards(settings: Settings, card_db: Path) -> Iterator[CardRepository]:
    repo = CardRepository(card_db, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def claim_host(c: TestClient) -> TestClient:
    """Make ``c`` the host's browser, the way the page does: post the server's secret to /api/host/session for the cookie."""
    secret = c.app.state.services.host_secret.value  # type: ignore[attr-defined]
    assert c.post("/api/host/session", json={"secret": secret}).status_code == 204
    return c


def guest(client: TestClient | None = None) -> dict[str, str]:
    """Headers for a request from someone who is not the host: the same client, but the host cookie is left out. Pass them as
    ``headers=guest(client)``. (A second ``TestClient`` on the same app starts with no cookies and is a guest as well.)"""
    return {"Cookie": ""}


@pytest.fixture()
def bare_client(settings: Settings) -> Iterator[TestClient]:
    """Client with no card database imported. It is the host."""
    with TestClient(create_app(settings)) as c:
        yield claim_host(c)


@pytest.fixture()
def client(settings: Settings, card_db: Path) -> Iterator[TestClient]:
    """The host's browser (it carries the host cookie); ``guest()`` gives the headers of anyone else."""
    with TestClient(create_app(settings)) as c:
        yield claim_host(c)
