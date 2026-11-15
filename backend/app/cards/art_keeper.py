"""Keep each saved deck's art for offline play (Settings → Keep deck art for offline play, on by default).

The norm at game night: a friend saved their decks on their own Fyodor at home, online; at the table there is only the LAN.
So whenever a deck is created, imported or saved while this computer may go online (``FYODOR_ALLOW_NETWORK``), the art for the
deck's own printings and the tokens they make is downloaded in the background, quietly (the Decks page shows a line while
it runs). Offline, the deck waits in a small list kept in the data folder (``art-keeper.json``) and is tried again when
Fyodor starts and every ``RETRY_MINUTES`` while it runs. Turning it off (small disks) stops new downloads; art already cached stays.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from app.services import Services

log = logging.getLogger(__name__)

RETRY_MINUTES = 15
DOWNLOADS = True
BATCH = 20  # images asked for at a time: a batch that fails entirely means we're offline, so we stop quietly


class ArtKeeper:
    def __init__(self, services: Services) -> None:
        self.services = services
        self.path: Path = services.settings.data_dir / "art-keeper.json"
        self.synchronous = False  # tests: do the work inline
        self.downloads = DOWNLOADS  # (the test suite turns this off: no test downloads art unless it asks to)
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._timer: threading.Thread | None = None
        self.enabled = True
        self.pending: list[str] = []
        self.progress: dict[str, Any] = {}
        self._load()

    # -- the list of decks waiting for art --------------------------------------------
    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return
        if isinstance(data, dict):
            self.enabled = data.get("enabled", True) is not False
            self.pending = [d for d in data.get("pending", []) if isinstance(d, str)][:1000]

    def _save(self) -> None:
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"enabled": self.enabled, "pending": self.pending}))
            os.replace(tmp, self.path)
        except OSError:
            log.debug("could not store the art keeper's list", exc_info=True)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {"enabled": self.enabled, "pending": len(self.pending), "running": self._busy(), **self.progress}

    def _busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def set_enabled(self, on: bool) -> None:
        with self._lock:
            self.enabled = on
            self._save()
        if on:
            self.kick()

    def want(self, deck_id: str) -> None:
        """A deck was saved: keep its art (now if this computer is online, later otherwise)."""
        with self._lock:
            if not self.enabled:
                return
            if deck_id not in self.pending:
                self.pending.append(deck_id)
                self._save()
        self.kick()

    # -- the work ----------------------------------------------------------------------
    def kick(self) -> None:
        """Work through the waiting decks, in the background (unless it already is, it's off or the network is)."""
        if not self.downloads or not self.enabled or not self.services.settings.allow_network or not self.pending:
            return
        if self.synchronous:
            self._work()
            return
        with self._lock:
            if self._busy():
                return
            self._thread = threading.Thread(target=self._work, name="art-keeper", daemon=True)
            self._thread.start()

    def _work(self) -> None:
        with self._lock:
            todo = list(self.pending)
        for deck_id in todo:  # each waiting deck once per pass: one whose art came only in part waits for the next pass
            if self._stop.is_set():
                break
            with self._lock:
                if not self.enabled:
                    break
            done = self._keep(deck_id)
            if done is None:
                break  # offline (or turned off): the deck waits for the next try
            if done:
                with self._lock:
                    if deck_id in self.pending:
                        self.pending.remove(deck_id)
                    self._save()
        with self._lock:
            self.progress = {}

    def _keep(self, deck_id: str) -> bool | None:
        """Download the deck's missing art. True when it's all here; False when some of it failed (try that again later);
        None when the network isn't there (stop: try again later)."""
        from app.cards.repository import CardDatabaseUnavailable
        from app.decks.repository import DeckNotFound

        services = self.services
        try:
            deck = services.decks.get(deck_id)
        except DeckNotFound:
            return True  # deleted meanwhile: nothing to keep
        ids = list(dict.fromkeys(e.printing_id for e in deck.entries if e.printing_id))
        # and the tokens its cards make, so the Bag of Extras and the table show them as printed offline too
        with contextlib.suppress(CardDatabaseUnavailable):
            ids += [t["id"] for c in services.cards.get_many(ids).values() for t in c.get("related_tokens") or []]
        ids = list(dict.fromkeys(ids))
        missing = [pid for pid in ids if not services.images.has(pid)]
        with self._lock:
            self.progress = {"deck": deck.name, "done": 0, "total": len(missing)}
        failed = 0
        for start in range(0, len(missing), BATCH):
            if self._stop.is_set() or not self.enabled:
                return None
            batch = missing[start : start + BATCH]
            try:
                report = services.fetch_artwork(batch, lambda *_: None, tokens=False)
            except (httpx.HTTPError, OSError) as exc:
                log.info("Deck art for %s waits until this computer is online (%s)", deck.name, exc)
                return None
            if report.requested and report.failed >= report.requested:
                log.info("Deck art for %s waits until this computer is online", deck.name)
                return None
            failed += report.failed
            with self._lock:
                self.progress = {"deck": deck.name, "done": min(len(missing), start + len(batch)), "total": len(missing)}
        if failed:
            log.info("Deck art for %s: %d image(s) failed; tried again later", deck.name, failed)
        return not failed

    # -- while Fyodor runs ---------------------------------------------------------------
    def start(self) -> None:
        """Try the waiting decks now, and again every ``RETRY_MINUTES``."""
        self.kick()

        def again() -> None:
            while not self._stop.wait(RETRY_MINUTES * 60):
                self.kick()

        self._timer = threading.Thread(target=again, name="art-keeper-retry", daemon=True)
        self._timer.start()

    def stop(self) -> None:
        self._stop.set()
