"""Automatic backups, like Tabletop Simulator's rotating autosave: nobody has to remember to press anything.

A small background thread makes a backup (``create_backup(..., reason=...)``):

* at start-up, when there is something worth keeping and the newest backup is more than a day old;
* every ``interval`` minutes, but only if the app database changed since the last backup;
* soon after a game result is recorded (``soon("after a recorded game")``).

Rotation is ``backup.prune``: the newest automatic backups plus one per day for a week, kept apart from the hand-made
ones. With ``copy_dir`` (FYODOR_BACKUP_COPY_DIR) every backup is mirrored to a second folder, so a dead disk doesn't
take the backups with it. A failed backup is logged and shown in Settings; it never stops the table.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.storage.backup import list_backups

log = logging.getLogger(__name__)

STARTUP_IF_OLDER_THAN = 20 * 3600  # one start-up backup per game-night day, not one per restart


class AutoBackups:
    def __init__(self, *, data_dir: Path, make: Callable[[str], dict[str, Any]], changes: Callable[[], int],
                 has_data: Callable[[], bool], interval_minutes: int, copy_dir: Path | None) -> None:
        self.data_dir = data_dir
        self.interval = max(0, interval_minutes)
        self.copy_dir = copy_dir
        self._make, self._changes, self._has_data = make, changes, has_data
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._pending: str | None = None
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._seen = changes()
        self.last: dict[str, Any] | None = None
        self.last_error: str | None = None

    @property
    def enabled(self) -> bool:
        return self.interval > 0

    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="fyodor-autobackup", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=10)

    def soon(self, reason: str) -> None:
        """Ask for a backup on the background thread (a recorded game, …); a no-op when automatic backups are off."""
        if not self.enabled:
            return
        with self._lock:
            self._pending = reason
        self._wake.set()

    # -- the work (also called directly by the tests) ------------------------------------------------------------
    def startup(self) -> dict[str, Any] | None:
        newest = list_backups(self.data_dir)[:1]
        if not self._has_data() or (newest and time.time() - newest[0]["mtime"] < STARTUP_IF_OLDER_THAN):
            return None
        return self._backup("start-up")

    def tick(self, reason: str = "while playing") -> dict[str, Any] | None:
        """Back up if anything changed since the last backup (a recorded game is a change too)."""
        if self._changes() == self._seen:
            return None
        return self._backup(reason)

    def run_pending(self) -> dict[str, Any] | None:
        with self._lock:
            reason, self._pending = self._pending, None
        return self.tick(reason) if reason else None

    def status(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "interval_minutes": self.interval,
                "copy_dir": str(self.copy_dir) if self.copy_dir else None, "last": self.last, "last_error": self.last_error}

    def _backup(self, reason: str) -> dict[str, Any] | None:
        seen = self._changes()
        try:
            made = self._make(reason)
        except Exception as exc:  # noqa: BLE001 - a backup must never take the table down; Settings shows the error
            log.exception("Automatic backup (%s) failed", reason)
            self.last_error = f"{reason}: {exc}"[:300]
            return None
        self._seen, self.last, self.last_error = seen, made, made.get("copy_error")
        log.info("Automatic backup (%s): %s", reason, made["name"])
        return made

    def _loop(self) -> None:
        self.startup()
        while not self._stop.is_set():
            woken = self._wake.wait(timeout=self.interval * 60)
            if self._stop.is_set():
                return
            self._wake.clear()
            if woken:
                self.run_pending()
            else:
                self.tick()
