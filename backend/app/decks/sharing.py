"""-- deck sharing -- friends' Fyodors on the network may browse the decks this computer shares (GET /api/lan/decks) and copy
one. Off until the owner turns it on (Settings → Share my decks on the network); then every deck (``all``) or only the decks
marked Shared. Only names, commanders and card lists leave this computer: never notes, folders, sources or saved rows."""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.decks.models import Deck

FILE = "deck-sharing.json"


def load(data_dir: Path) -> dict[str, bool]:
    try:
        data = json.loads((data_dir / FILE).read_text())
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    return {"enabled": data.get("enabled") is True, "all": data.get("all") is True}


def save(data_dir: Path, *, enabled: bool, all: bool) -> dict[str, bool]:  # noqa: A002 - the setting's name
    prefs = {"enabled": enabled, "all": all}
    tmp = data_dir / (FILE + ".tmp")
    tmp.write_text(json.dumps(prefs))
    os.replace(tmp, data_dir / FILE)
    return prefs


def shared(decks: list[Deck], prefs: dict[str, bool]) -> list[Deck]:
    """The decks friends may see: none while sharing is off."""
    if not prefs["enabled"]:
        return []
    return [d for d in decks if prefs["all"] or d.shared]
