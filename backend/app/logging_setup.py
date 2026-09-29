from __future__ import annotations

import contextlib
import logging
import time
from collections import deque

# The last warnings/errors, kept in memory for the local diagnostics export (never sent anywhere).
RECENT_PROBLEMS: deque[dict[str, str]] = deque(maxlen=200)


class _RecentProblems(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        with contextlib.suppress(Exception):  # logging must never raise
            RECENT_PROBLEMS.append({
                "time": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created)),
                "level": record.levelname, "logger": record.name, "message": record.getMessage()[:500],
            })


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    root = logging.getLogger()
    if not any(isinstance(h, _RecentProblems) for h in root.handlers):
        handler = _RecentProblems(level=logging.WARNING)
        root.addHandler(handler)
