"""Version information shown unobtrusively (diagnostics, About, exported rules scenarios)."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from app import __version__
from app.config import REPO_ROOT


@lru_cache(maxsize=1)
def commit() -> str | None:
    """The git commit this build runs from (FYODOR_BUILD for packaged builds). Read from files,
    never by running git."""
    if os.environ.get("FYODOR_BUILD"):
        return os.environ["FYODOR_BUILD"][:40]
    git = REPO_ROOT / ".git"
    try:
        head = (git / "HEAD").read_text("utf-8").strip()
        if not head.startswith("ref: "):
            return head[:12]
        ref = head[5:]
        path = git / ref
        if path.is_file():
            return path.read_text("utf-8").strip()[:12]
        packed = git / "packed-refs"
        if packed.is_file():
            for line in packed.read_text("utf-8").splitlines():
                if line.endswith(" " + ref):
                    return line.split(" ", 1)[0][:12]
    except OSError:
        return None
    return None


def build_info() -> dict[str, Any]:
    from app.rules.engine import RULES_ENGINE_VERSION
    from app.rules.research import current_version
    from app.storage.save_format import SAVE_VERSION

    return {
        "version": __version__, "commit": commit(), "save_version": SAVE_VERSION,
        "rules_engine_version": RULES_ENGINE_VERSION, "comprehensive_rules": current_version(),
    }
