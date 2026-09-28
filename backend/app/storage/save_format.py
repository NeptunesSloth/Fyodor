"""Versioned save-file format and migrations.

A save payload is JSON::

    {"format": "fyodor-save", "version": 1, "saved_at": ..., "state": {...}, "history": {...}}

Bump ``SAVE_VERSION`` whenever GameState changes incompatibly and add a migration function
that upgrades a payload from the previous version.
"""

from __future__ import annotations

import json
import zlib
from collections.abc import Callable
from typing import Any

SAVE_FORMAT = "fyodor-save"
SAVE_VERSION = 1
MAX_SAVE_BYTES = 64 * 1024 * 1024  # decompressed

Migration = Callable[[dict[str, Any]], dict[str, Any]]
# MIGRATIONS[n] upgrades a version-n payload to version n + 1.
MIGRATIONS: dict[int, Migration] = {}


class SaveFormatError(ValueError):
    pass


def encode(payload: dict[str, Any]) -> bytes:
    return zlib.compress(json.dumps(payload, separators=(",", ":")).encode("utf-8"), level=6)


def decode(blob: bytes) -> dict[str, Any]:
    try:
        inflater = zlib.decompressobj()
        raw = inflater.decompress(blob, MAX_SAVE_BYTES)
        if inflater.unconsumed_tail:
            raise SaveFormatError("Save file is too large")
        payload = json.loads(raw)
    except (zlib.error, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SaveFormatError(f"Corrupt save: {exc}") from exc
    return migrate(payload)


def migrate(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("format") != SAVE_FORMAT:
        raise SaveFormatError("Not a Fyodor save")
    version = payload.get("version")
    if not isinstance(version, int) or version < 1:
        raise SaveFormatError("Save has no valid version")
    if version > SAVE_VERSION:
        raise SaveFormatError(f"Save version {version} is newer than this app supports ({SAVE_VERSION})")
    while version < SAVE_VERSION:
        payload = MIGRATIONS[version](payload)
        version += 1
        payload["version"] = version
    return payload
