from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.config import Settings, load_settings
from app.main import create_app
from tests.fixtures.cards import fixture_cards


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


@pytest.fixture()
def bare_client(settings: Settings) -> Iterator[TestClient]:
    """Client with no card database imported."""
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture()
def client(settings: Settings, card_db: Path) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as c:
        yield c
