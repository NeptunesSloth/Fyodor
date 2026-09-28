"""Service container: owns long-lived resources (DB connections, repositories, game hub)."""

from __future__ import annotations

import logging
import threading

from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.config import Settings
from app.decks.repository import DeckRepository
from app.storage.app_db import open_app_db

log = logging.getLogger(__name__)


class Services:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        settings.ensure_dirs()
        self.app_db = open_app_db(settings.app_db_path)
        self.app_db_lock = threading.RLock()
        self.decks = DeckRepository(self.app_db, self.app_db_lock)
        self.images = ImageStore(settings.images_dir)
        self.cards = CardRepository(settings.cards_db_path, self.images)

    def health(self) -> dict[str, object]:
        return {"card_database": self.cards.stats()}

    def close(self) -> None:
        self.cards.close()
        self.app_db.close()
