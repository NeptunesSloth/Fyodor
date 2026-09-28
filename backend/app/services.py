"""Service container: owns long-lived resources (DB connections, repositories, game hub)."""

from __future__ import annotations

import logging
import threading

from app.assistant import OllamaAssistant, RulesAssistant
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.config import Settings
from app.decks.repository import DeckRepository
from app.multiplayer.hub import GameHub, Room
from app.rules import RulesRegistry
from app.storage.app_db import open_app_db
from app.storage.saves import SaveRepository

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
        self.saves = SaveRepository(self.app_db, self.app_db_lock)
        self.hub = GameHub(autosave=self.autosave, autosave_every=settings.autosave_every)
        self.rules = RulesRegistry()  # no modules ship enabled; see app/rules/__init__.py
        self.assistant: RulesAssistant | None = (
            OllamaAssistant(settings.assistant_url, settings.assistant_model) if settings.assistant_url else None
        )

    def autosave(self, room: Room) -> None:
        state = room.session.state
        self.saves.save(state, room.session.history, name=f"{state.name} (autosave)", autosave=True)
        log.debug("Autosaved game %s at action %d", state.id, state.seq)

    def health(self) -> dict[str, object]:
        return {
            "card_database": self.cards.stats(),
            "games_active": len(self.hub.rooms),
            "assistant_enabled": self.assistant is not None,
        }

    def close(self) -> None:
        for room in list(self.hub.rooms.values()):
            try:
                self.autosave(room)
            except Exception:  # noqa: BLE001 - shutting down; log and continue closing
                log.exception("Final autosave failed for %s", room.id)
        self.cards.close()
        self.app_db.close()
