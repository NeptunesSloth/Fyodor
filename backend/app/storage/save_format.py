"""Versioned save-file format and migrations.

A save payload is JSON::

    {"format": "fyodor-save", "version": 1, "saved_at": ..., "state": {...}, "history": {...}}

Bump ``SAVE_VERSION`` whenever GameState changes incompatibly and add a migration function
that upgrades a payload from the previous version.
"""

from __future__ import annotations

import json
import secrets
import zlib
from collections.abc import Callable
from typing import Any

SAVE_FORMAT = "fyodor-save"
SAVE_VERSION = 3
MAX_SAVE_BYTES = 64 * 1024 * 1024  # decompressed

Migration = Callable[[dict[str, Any]], dict[str, Any]]


def _v1_state_to_v2(state: dict[str, Any], salt: str) -> None:
    """v1 remembered who had *ever* seen a card (``known_to``); v2 only models current visibility."""
    for card in (state.get("cards") or {}).values():
        was_revealed = bool(card.pop("revealed", False))
        card.pop("known_to", None)  # remembered sightings are deliberately dropped
        card["revealed_to"] = ["*"] if was_revealed else []
    searches = state.pop("searches", None) or {}
    state["views"] = [
        {"id": f"search-{viewer}", "viewer": viewer, "zone": zone, "kind": "search", "card_ids": []}
        for viewer, zone in searches.items()
    ]
    state.setdefault("hidden_salt", salt)


def _v1_to_v2(payload: dict[str, Any]) -> dict[str, Any]:
    salt = secrets.token_hex(16)  # shared by state and history base so replay stays consistent
    if isinstance(payload.get("state"), dict):
        _v1_state_to_v2(payload["state"], salt)
    history = payload.get("history")
    if isinstance(history, dict) and isinstance(history.get("base"), dict):
        _v1_state_to_v2(history["base"], salt)
    return payload


RETIRED_ACTIONS = {"add_reminder", "dismiss_reminder"}  # the step-reminder system was removed in v3


def _v2_state_to_v3(state: dict[str, Any]) -> None:
    state.pop("reminders", None)
    for card in (state.get("cards") or {}).values():
        card.setdefault("face_down_kind", None)


def _v2_to_v3(payload: dict[str, Any]) -> dict[str, Any]:
    """v3 drops step reminders (state and undo history) and adds face-down kinds / commander casts."""
    if isinstance(payload.get("state"), dict):
        _v2_state_to_v3(payload["state"])
    history = payload.get("history")
    if isinstance(history, dict):
        if isinstance(history.get("base"), dict):
            _v2_state_to_v3(history["base"])
        actions = history.get("actions") or []
        cursor = int(history.get("cursor", len(actions)))
        kept = [a for a in actions if not (isinstance(a, dict) and a.get("type") in RETIRED_ACTIONS)]
        removed_before_cursor = sum(
            1 for a in actions[:cursor] if isinstance(a, dict) and a.get("type") in RETIRED_ACTIONS
        )
        history["actions"] = kept
        history["cursor"] = max(0, cursor - removed_before_cursor)
    return payload


# MIGRATIONS[n] upgrades a version-n payload to version n + 1.
MIGRATIONS: dict[int, Migration] = {1: _v1_to_v2, 2: _v2_to_v3}


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
    if version < SAVE_VERSION:
        payload["migrated_from"] = version
    while version < SAVE_VERSION:
        payload = MIGRATIONS[version](payload)
        version += 1
        payload["version"] = version
    return payload
