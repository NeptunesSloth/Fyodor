"""Service container: owns long-lived resources (DB connections, repositories, game hub)."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from app.assets.store import AssetNotFound, AssetStore
from app.assistant import OllamaAssistant, RulesAssistant
from app.cards.downloader import ImageReport, download_images, image_jobs_from_rows, make_client
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.config import Settings
from app.decks import archidekt
from app.decks.repository import DeckRepository
from app.jobs import JobManager
from app.multiplayer.hub import GameHub, Room
from app.rules import RulesRegistry
from app.stats.repository import PodStats
from app.storage.app_db import open_app_db
from app.storage.macros import MacroRepository
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
        self.stats = PodStats(self.app_db, self.app_db_lock)
        self.macros = MacroRepository(self.app_db, self.app_db_lock)
        self.assets = AssetStore(self.app_db, self.app_db_lock, settings.assets_dir)
        self.hub = GameHub(autosave=self.autosave, autosave_every=settings.autosave_every, asset_info=self.asset_info)
        self.jobs = JobManager()
        self.source_cache: dict[str, tuple[float, Any]] = {}
        self.rules = RulesRegistry()  # no modules ship enabled; see app/rules/__init__.py
        self.assistant: RulesAssistant | None = (
            OllamaAssistant(settings.assistant_url, settings.assistant_model) if settings.assistant_url else None
        )

    def archidekt_fetch(self, deck_id: str) -> dict[str, Any]:
        """Fetch a public Archidekt deck (only called on explicit user action)."""
        return archidekt.fetch_deck(deck_id, user_agent=self.settings.user_agent)

    def cache_artwork(self, printing_ids: list[str], progress: Callable[[int, int, int], None]) -> str:
        """Download missing images for these printings and the tokens they create."""
        ids = list(dict.fromkeys(printing_ids))
        cards = self.cards.get_many(ids)
        token_ids = [t["id"] for c in cards.values() for t in c.get("related_tokens") or []]
        rows = self.cards.image_rows([*ids, *dict.fromkeys(token_ids)])
        jobs = image_jobs_from_rows(rows)

        def report(r: ImageReport) -> None:
            progress(r.downloaded + r.skipped + r.failed, r.requested, r.failed)

        with make_client(self.settings.user_agent, timeout=30.0) as client:
            result = download_images(client, self.images, jobs, workers=6, progress=report)
        return (f"{result.downloaded} downloaded, {result.skipped} already cached, {result.failed} failed"
                + (" — re-run to retry" if result.failed else ""))

    def asset_info(self, ids: set[str]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for aid in ids:
            try:
                a = self.assets.get(aid)
            except AssetNotFound:
                continue
            out[aid] = {"url": a["url"], "width": a["width"], "height": a["height"], "kind": a["kind"]}
        return out

    def assets_in_use(self) -> dict[str, list[str]]:
        """asset id -> where it's used (live tables)."""
        used: dict[str, list[str]] = {}
        for room in self.hub.rooms.values():
            if room.game is None:
                continue
            st = room.game.state
            for p in st.players.values():
                if p.sleeve:
                    used.setdefault(p.sleeve, []).append(f"{st.name}: {p.name}'s sleeves")
                if p.playmat:
                    used.setdefault(p.playmat.asset_id, []).append(f"{st.name}: {p.name}'s playmat")
            if st.table.playmat:
                used.setdefault(st.table.playmat.asset_id, []).append(f"{st.name}: table playmat")
        return used

    def autosave(self, room: Room) -> None:
        if not room.started:
            return  # nothing to save before the host starts the game
        state = room.session.state
        self.saves.save(state, room.session.history, name=f"{state.name} (autosave)", autosave=True,
                        extras={"table_snapshots": room.session.table_snapshots})
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
        self.jobs.shutdown()
        self.cards.close()
        self.app_db.close()
