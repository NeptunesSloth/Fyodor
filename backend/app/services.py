"""Service container: owns long-lived resources (DB connections, repositories, game hub)."""

from __future__ import annotations

import concurrent.futures
import contextlib
import json
import logging
import sqlite3
import threading
from collections.abc import Callable
from typing import Any

import httpx

from app.assets.store import AssetNotFound, AssetStore
from app.assistant import OllamaAssistant, RulesAssistant
from app.cards.art_folders import ArtFolders
from app.cards.art_keeper import ArtKeeper
from app.cards.downloader import (
    ImageReport,
    download_card_back,
    download_images,
    image_jobs_from_rows,
    make_client,
)
from app.cards.images import UUID_RE, ImageStore
from app.cards.linked import LinkedAssets
from app.cards.repository import CardDatabaseUnavailable, CardRepository
from app.cards.token_art import TokenArt
from app.config import Settings
from app.decks import archidekt
from app.decks.repository import DeckRepository
from app.game import engine
from app.game.actions import ACTION_ADAPTER
from app.game.session import GameSession
from app.hostauth import SECRET_FILE, HostSecret
from app.jobs import JobManager, ProgressFn
from app.multiplayer.handoff import Handoffs
from app.multiplayer.hub import GameHub, Room
from app.netguard import AttemptLimiter, ConnectionCaps
from app.rules import RulesRegistry
from app.stats.repository import PodStats
from app.storage.app_db import MIGRATIONS as APP_MIGRATIONS
from app.storage.app_db import open_app_db
from app.storage.autobackup import AutoBackups
from app.storage.backup import (
    SYNCED_BROWSER_DECKS,
    RecoveryInfo,
    apply_pending_restore,
    create_backup,
    deck_art,
    list_backups,
    pre_migration_backup,
    quarantine_damaged,
)
from app.storage.journal import RoomJournal
from app.storage.macros import MacroRepository
from app.storage.saves import SaveRepository
from app.storage.taught import TaughtRepository
from app.tunnel.manager import TunnelManager

log = logging.getLogger(__name__)


def replay_journal(session: GameSession, entries: list[dict[str, Any]]) -> int:
    """Re-apply journaled changes on top of a checkpoint. Returns how many were applied."""
    done = 0
    for entry in entries:
        kind = entry.get("k")
        try:
            if kind == "do":
                action = ACTION_ADAPTER.validate_python(entry["a"])
                engine.apply(session.state, action)  # resolved actions replay exactly (randomness included)
                session.history.record(action, session.state)
            elif kind == "undo":
                session.state, _ = session.history.undo()
            elif kind == "redo":
                session.state, _ = session.history.redo(session.state)
            else:
                break
        except Exception:  # noqa: BLE001 - keep everything up to the last good change
            log.exception("Journal replay stopped at entry %d", done + 1)
            session.state = session.history.rebuild()
            break
        done += 1
    return done


class Services:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        settings.ensure_dirs()
        self.host_secret = HostSecret(settings.data_dir / SECRET_FILE)  # new on every start; see app/hostauth.py
        self.recovery: RecoveryInfo | None = None
        self.join_limiter_addr = AttemptLimiter(5, 900.0)  # wrong room codes and passwords, by client address
        self.host_limiter_addr = AttemptLimiter(5, 900.0)  # wrong host secrets, by client address (the right one is never refused)
        self.join_limiter_room = AttemptLimiter(30, 900.0)  # wrong passwords, by room code (a room that exists)
        # /api/join's password checks (PBKDF2, ~0.2 s each): a pool of their own, so joins waiting to be hashed never hold the threads
        # every other sync route runs on
        self.hash_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="pbkdf2")
        self.caps_seat = ConnectionCaps(4)  # open game sockets per seat ("<game id>:<seat>"): a tab, a spare window, a phone that has not timed out yet
        self.caps_addr = ConnectionCaps(24)  # open game sockets per client address, authenticated or not (hot-seat and the host's windows stay far under)
        self.tunnel = TunnelManager(settings)  # -- invite over the internet -- (its port is set by the launcher; app/tunnel/manager.py)
        self.extra_origins: set[str] = set()  # origins besides the server's own and settings.cors_origins that may post and open sockets
        self.app_db = self._open_app_db()
        self.app_db_lock = threading.RLock()
        self.decks = DeckRepository(self.app_db, self.app_db_lock)
        self.images = ImageStore(settings.images_dir)  # (its read-only art folders, the installer's seed/images first: art_folders below)
        self.cards = CardRepository(settings.cards_db_path, self.images)
        # -- art folders -- more read-only folders of pictures (the installer's seed/images is the first): docs/OFFLINE.md
        self.art_folders = ArtFolders(settings, self.images, on_change=self.cards.art.clear)
        self.saves = SaveRepository(self.app_db, self.app_db_lock)
        self.stats = PodStats(self.app_db, self.app_db_lock)
        self.macros = MacroRepository(self.app_db, self.app_db_lock)
        self.taught = TaughtRepository(self.app_db, self.app_db_lock)  # -- Teach Fyodor -- (new games start with its enabled entries)
        self.assets = AssetStore(self.app_db, self.app_db_lock, settings.assets_dir)
        self.journal = RoomJournal(self.app_db, self.app_db_lock)
        self.hub = GameHub(autosave=self.autosave, autosave_every=settings.autosave_every, asset_info=self.asset_info,
                           journal=self.journal, decks=self.decks)
        self.handoffs = Handoffs()  # decks a joining player brought from their own computer (memory only)
        self.art_keeper = ArtKeeper(self)  # each saved deck's art, kept for offline play while online
        self.jobs = JobManager()
        self.http_client: Callable[..., httpx.Client] = make_client  # online features use this (the tests swap it)
        self.linked = LinkedAssets(settings, self.images, lambda: self.http_client)  # the card back and the mana symbols
        self.token_art = TokenArt(settings, self.images, self.cards, lambda: self.http_client)  # token pictures, when first shown
        self.source_cache: dict[str, tuple[float, Any]] = {}
        self.rules = RulesRegistry()  # no modules ship enabled; see app/rules/__init__.py
        self.assistant: RulesAssistant | None = (
            OllamaAssistant(settings.assistant_url, settings.assistant_model) if settings.assistant_url else None
        )
        self.recovered: list[dict[str, Any]] = self.recover_rooms()
        self.autobackups = AutoBackups(
            data_dir=settings.data_dir, interval_minutes=settings.auto_backup_minutes, copy_dir=settings.backup_copy_dir,
            make=lambda reason: self.backup(reason=reason), changes=lambda: self.app_db.total_changes + self.browser_decks_saved, has_data=self._has_data)

    def recover_rooms(self) -> list[dict[str, Any]]:
        """Bring back every table that was live when Fyodor stopped (crash or restart)."""
        out: list[dict[str, Any]] = []
        for live in self.journal.live():
            if live.checkpoint is None:
                self.journal.forget(live.game_id)  # never checkpointed: nothing to rebuild from
                continue
            try:
                state, history = self.saves.load(live.checkpoint, history_limit=self.settings.history_limit)
                session = GameSession(state, cards=self.cards, history=history, history_limit=self.settings.history_limit,
                                      rules=self.rules)
                snaps = self.saves.extras(live.checkpoint).get("table_snapshots")
                if isinstance(snaps, list):
                    session.table_snapshots = [x for x in snaps if isinstance(x, dict) and isinstance(x.get("state"), dict)]
                replayed = replay_journal(session, live.entries)
            except Exception:  # noqa: BLE001 - a damaged table must not stop the others from coming back
                log.exception("Could not recover table %s; its autosaves are still in Saves", live.game_id)
                self.journal.forget(live.game_id)
                continue
            room = self.hub.restore(live.meta, session, live.client_actions)
            session.notice("Fyodor restarted — the table was restored where it left off.")  # (every table reconnects on its own)
            self.autosave(room)  # a fresh checkpoint (compacts the journal)
            out.append({"game_id": room.id, "name": session.state.name, "replayed": replayed, "entries": len(live.entries)})
            log.info("Recovered table %s (%s): %d of %d journal entries replayed", room.id, session.state.name,
                     replayed, len(live.entries))
        return out

    def _open_app_db(self) -> sqlite3.Connection:
        """Open app.sqlite: apply a staged restore, back up before migrating, recover if damaged."""
        path = self.settings.app_db_path
        if apply_pending_restore(self.settings.data_dir, path, self.settings.assets_dir, self.settings.images_dir):
            log.warning("A backup was restored at start-up")
        pre_migration_backup(path, len(APP_MIGRATIONS))
        try:
            conn = open_app_db(path)
            try:
                check = conn.execute("PRAGMA quick_check").fetchone()[0]
            except sqlite3.DatabaseError:
                conn.close()  # closed before the file is moved aside (Windows can't move an open file)
                raise
            if check != "ok":
                conn.close()
                raise sqlite3.DatabaseError(f"integrity check: {check}")
            return conn
        except sqlite3.DatabaseError as exc:
            moved = quarantine_damaged(path)
            log.error("app.sqlite is damaged (%s); moved to %s and starting in recovery mode", exc, moved)
            self.recovery = RecoveryInfo(reason=str(exc)[:200], moved_to=moved.name,
                                         backups=[b["name"] for b in list_backups(self.settings.data_dir)])
            return open_app_db(path)

    def backup(self, *, reason: str | None = None, browser_decks: list[Any] | None = None,
               art: bool | None = None) -> dict[str, Any]:
        """A backup now: by hand (``reason`` None) or automatic. Mirrored to FYODOR_BACKUP_COPY_DIR when set.
        ``browser_decks``: the asking browser's "My decks", carried in the backup too. ``art`` (by default: hand-made
        backups only): the cached card art the saved decks need offline, so a restore on an offline computer has it."""
        want_art = reason is None if art is None else art
        return create_backup(self.settings.data_dir, self.app_db, self.app_db_lock, self.settings.assets_dir, reason=reason,
                             copy_dir=self.settings.backup_copy_dir, browser_decks=browser_decks,
                             art=deck_art(self.images, self._deck_printings(browser_decks)) if want_art else None)

    def _deck_printings(self, browser_decks: list[Any] | None) -> list[str]:
        """Every printing the saved decks (and the browser's My decks) use, plus the tokens they make (as the art keeper
        keeps them, app/cards/art_keeper.py)."""
        ids = [e.printing_id for d in self.decks.list_all() for e in d.entries if e.printing_id]
        if browser_decks is None:  # the host browser's mirrored copy, as the backup itself carries it
            with contextlib.suppress(OSError, ValueError):
                browser_decks = json.loads((self.settings.data_dir / SYNCED_BROWSER_DECKS).read_bytes())
        for deck in browser_decks if isinstance(browser_decks, list) else []:
            entries = deck.get("entries") if isinstance(deck, dict) else None
            for e in entries if isinstance(entries, list) else []:
                if isinstance(e, dict) and isinstance(e.get("printing_id"), str):
                    ids.append(e["printing_id"])
        ids = [i for i in dict.fromkeys(ids) if UUID_RE.match(i)]
        with contextlib.suppress(CardDatabaseUnavailable):
            ids += [t["id"] for c in self.cards.get_many(ids).values() for t in c.get("related_tokens") or []]
        return list(dict.fromkeys(ids))

    browser_decks_saved = 0  # times the host browser's My decks mirror was rewritten: a change automatic backups count

    def _has_data(self) -> bool:
        synced = self.settings.data_dir / SYNCED_BROWSER_DECKS
        if synced.is_file() and synced.stat().st_size > 2:  # My decks alone are worth a backup ("[]" is none)
            return True
        with self.app_db_lock:
            return any(self.app_db.execute(f"SELECT 1 FROM {t} LIMIT 1").fetchone()  # noqa: S608 - fixed names
                       for t in ("decks", "saves", "game_results"))

    def archidekt_fetch(self, deck_id: str) -> dict[str, Any]:
        """Fetch a public Archidekt deck (only called on explicit user action)."""
        return archidekt.fetch_deck(deck_id, user_agent=self.settings.user_agent)

    def fetch_artwork(self, printing_ids: list[str], progress: ProgressFn, *, tokens: bool = True) -> ImageReport:
        """Download missing images for these printings (and, with ``tokens``, the tokens they create)."""
        ids = list(dict.fromkeys(printing_ids))
        token_ids: list[str] = []
        if tokens:
            cards = self.cards.get_many(ids)
            token_ids = [t["id"] for c in cards.values() for t in c.get("related_tokens") or []]
        rows = self.cards.image_rows([*ids, *dict.fromkeys(token_ids)])
        jobs = image_jobs_from_rows(rows)

        def report(r: ImageReport) -> None:
            progress(r.downloaded + r.skipped + r.failed, r.requested, r.failed)

        with make_client(self.settings.user_agent, timeout=30.0) as client:
            result = download_images(client, self.images, jobs, workers=6, progress=report)
            download_card_back(client, self.images)  # the Magic card back, for library piles and hidden cards
        return result

    def related_tokens(self, printing_id: str) -> list[str]:
        """The tokens a printing makes (its Scryfall related tokens), for a deck's Bag of Extras; none without a card database."""
        try:
            return [t["id"] for t in self.cards.related_tokens(printing_id)]
        except CardDatabaseUnavailable:
            return []

    def cache_artwork(self, printing_ids: list[str], progress: ProgressFn) -> str:
        """Download missing images for these printings and the tokens they create."""
        result = self.fetch_artwork(printing_ids, progress)
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
        if not room.started or room.practice is not None:
            return  # nothing to save before the host starts the game; a practice table is never saved (ELIMINATION_HUB.md)
        state = room.session.state
        saved = self.saves.save(state, room.session.history, name=f"{state.name} (autosave)", autosave=True,
                                extras={"table_snapshots": room.session.table_snapshots})
        if room.id in self.hub.rooms:
            self.hub.persist(room)
            self.journal.checkpoint(room.id, saved["id"])
        log.debug("Autosaved game %s at action %d", state.id, state.seq)

    def health(self) -> dict[str, object]:
        out: dict[str, object] = {
            "card_database": self.cards.stats(),
            "games_active": len(self.hub.rooms),
            "assistant_enabled": self.assistant is not None,
        }
        if self.recovery is not None:
            out["recovery"] = {"reason": self.recovery.reason, "moved_to": self.recovery.moved_to,
                               "backups": self.recovery.backups}
        if self.recovered:
            out["recovered_tables"] = [{"game_id": r["game_id"], "name": r["name"]} for r in self.recovered]
        return out

    def close(self) -> None:
        self.tunnel.stop()  # first: nobody reaches the tables over the internet while they are saved and closed
        for room in list(self.hub.rooms.values()):
            try:
                self.autosave(room)
            except Exception:  # noqa: BLE001 - shutting down; log and continue closing
                log.exception("Final autosave failed for %s", room.id)
        self.autobackups.stop()
        self.art_keeper.stop()
        self.jobs.shutdown()
        # (a join still hashing finishes, queued ones are dropped; called from the lifespan, so the loop waits up to one hash, ~0.2 s)
        self.hash_pool.shutdown(wait=True, cancel_futures=True)
        self.cards.close()
        self.app_db.close()
