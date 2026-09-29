"""Where researched rules live: ``data/rules/comprehensive_rules/<effective date>/``."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.config import REPO_ROOT
from app.rules.research import RULES_DIR, versions

REPORTS_DIR = REPO_ROOT / "data" / "reports"
BULLETINS = REPO_ROOT / "data" / "rules" / "bulletins.json"
TEXT_NAME = "comprehensive_rules.txt"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def latest(root: Path = RULES_DIR) -> dict[str, Any] | None:
    found = versions(root)
    return found[-1] if found else None


def latest_text(root: Path = RULES_DIR) -> str | None:
    meta = latest(root)
    if meta is None:
        return None
    return (root / meta["dir"] / TEXT_NAME).read_text("utf-8")


def save(text: str, meta: dict[str, Any], root: Path = RULES_DIR) -> Path:
    """Store one version. The directory is named after the effective date (unique per release)."""
    folder = root / str(meta["effective_date"])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / TEXT_NAME).write_text(text, "utf-8")
    (folder / "sha256.txt").write_text(meta["sha256"] + f"  {TEXT_NAME}\n", "utf-8")
    (folder / "source.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", "utf-8")
    return folder
