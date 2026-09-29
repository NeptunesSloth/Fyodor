"""What the engine knows about the Comprehensive Rules it was built against (read-only, offline).

The rules text itself is fetched and indexed by the developer tool ``tools/rules_research``
into ``data/rules/comprehensive_rules/<version>/`` (committed with the code). At runtime the app
only reads which version that was, for diagnostics and exported rules scenarios. Nothing here
ever goes online.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import REPO_ROOT

RULES_DIR = REPO_ROOT / "data" / "rules" / "comprehensive_rules"


def versions(root: Path = RULES_DIR) -> list[dict[str, Any]]:
    """Stored rules versions, oldest first (each with its ``source.json`` metadata)."""
    out = []
    if root.is_dir():
        for d in sorted(p for p in root.iterdir() if p.is_dir()):
            meta = d / "source.json"
            if meta.is_file():
                try:
                    out.append({"dir": d.name, **json.loads(meta.read_text("utf-8"))})
                except (OSError, ValueError):
                    continue
    return out


@lru_cache(maxsize=1)
def current_version() -> str | None:
    found = versions()
    if not found:
        return None
    latest = found[-1]
    return str(latest.get("effective_date") or latest["dir"])
