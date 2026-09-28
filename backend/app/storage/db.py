"""SQLite connection helpers and a minimal numbered-migration runner."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger(__name__)


def connect(path: Path | str, *, readonly: bool = False) -> sqlite3.Connection:
    """Open a connection with sane defaults (row factory, FK enforcement, WAL)."""
    if isinstance(path, Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        uri = f"file:{path.as_posix()}{'?mode=ro' if readonly else ''}"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    else:
        conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if not readonly and path != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Explicit transaction that commits on success and rolls back on error."""
    conn.execute("BEGIN")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def migrate(conn: sqlite3.Connection, migrations: Sequence[str], *, name: str) -> int:
    """Apply numbered migrations (index + 1 = version). Returns the resulting version."""
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    current = row["version"] if row else 0
    if row is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (0)")
        conn.commit()
    for version, script in enumerate(migrations, start=1):
        if version <= current:
            continue
        log.info("Applying %s migration %d", name, version)
        conn.executescript(f"BEGIN;\n{script}\nUPDATE schema_version SET version = {version};\nCOMMIT;")
        current = version
    return current
