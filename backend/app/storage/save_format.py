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
SAVE_VERSION = 7
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


def _v3_state_to_v4(state: dict[str, Any]) -> None:
    for card in (state.get("cards") or {}).values():
        if "origin" in card:
            continue
        zone = str(card.get("zone", "")).split(":")[-1]
        card["origin"] = "command" if card.get("commander_key") else zone if zone in ("sideboard", "companion") else "library"


def _v3_to_v4(payload: dict[str, Any]) -> dict[str, Any]:
    """v4 remembers where each card starts (for Reset deck); infer it for older games."""
    if isinstance(payload.get("state"), dict):
        _v3_state_to_v4(payload["state"])
    history = payload.get("history")
    if isinstance(history, dict) and isinstance(history.get("base"), dict):
        _v3_state_to_v4(history["base"])
    return payload


def _v4_state_to_v5(state: dict[str, Any]) -> None:
    state.setdefault("rules", None)
    settings = state.get("settings")
    if isinstance(settings, dict):
        settings.setdefault("automation", "off")


def _v4_to_v5(payload: dict[str, Any]) -> dict[str, Any]:
    """v5 adds rules automation (``settings.automation``, ``rules``); older games are sandbox games."""
    if isinstance(payload.get("state"), dict):
        _v4_state_to_v5(payload["state"])
    history = payload.get("history")
    if isinstance(history, dict) and isinstance(history.get("base"), dict):
        _v4_state_to_v5(history["base"])
    return payload


FULL_OPTIONS = {
    "auto_mana_payment": True, "auto_combat_damage": True, "auto_sba": True, "auto_priority_pass": True,
    "auto_cleanup": True, "auto_token_creation": True, "auto_counters": True, "auto_trigger_stacking": True,
    "auto_shuffle": True, "highlights": "full",
}


def _v5_rules_to_v6(rules: Any) -> None:
    """M14 stops become per-player preferences (RESPONSE AUTO, or ON for players who had smart
    passing off)."""
    if not isinstance(rules, dict):
        return
    stops = rules.pop("stops", None) or {}
    prefs = rules.setdefault("prefs", {})
    for pid, st in stops.items():
        if isinstance(st, dict) and pid not in prefs:
            prefs[pid] = {
                "stops_my_turn": st.get("own", ["main1", "main2"]), "stops_their_turn": st.get("others", []),
                "hold_priority": bool(st.get("hold_priority", False)),
                "response": "auto" if st.get("smart_pass", True) else "on",
            }


def _v5_state_to_v6(state: dict[str, Any]) -> None:
    settings = state.get("settings")
    if isinstance(settings, dict):
        # v5 had one automation level, "rules" (= today's FULL). OFF games stay OFF: FULL is never
        # switched on silently.
        if settings.get("automation") == "rules":
            settings["automation"] = "full"
            settings["automation_options"] = dict(FULL_OPTIONS)
        else:
            settings["automation"] = "off"
    _v5_rules_to_v6(state.get("rules"))


def _v5_steps_to_v6(steps: Any) -> None:
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        if step.get("type") == "rules_sync":
            _v5_rules_to_v6(step.get("rules"))
        elif step.get("type") == "configure" and step.get("automation") == "rules":
            step["automation"] = "full"


def _v5_to_v6(payload: dict[str, Any]) -> dict[str, Any]:
    """v6 splits automation into OFF / ASSISTED / FULL with per-feature options, and per-player
    automation preferences replace M14's stops (in the state and in recorded history)."""
    if isinstance(payload.get("state"), dict):
        _v5_state_to_v6(payload["state"])
    history = payload.get("history")
    if isinstance(history, dict):
        if isinstance(history.get("base"), dict):
            _v5_state_to_v6(history["base"])
        actions = history.get("actions") or []
        _v5_steps_to_v6(actions)
        for action in actions:
            if isinstance(action, dict) and isinstance(action.get("r"), list):
                _v5_steps_to_v6(action["r"])
    return payload


def _v6_to_v7(payload: dict[str, Any]) -> dict[str, Any]:
    """v7: a card that becomes face down where others see it gets a new id (ops.renumber). The moves recorded before did not:
    replaying them (undo, history) keeps their ids, as they were played."""
    def walk(v: Any) -> None:
        if isinstance(v, dict):
            if v.get("type") in ("move", "mill", "put_top_face_down") and "actor" in v:
                v.setdefault("keep_ids", True)
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(payload.get("history"))
    walk(payload.get("state"))  # (an intent waiting in a response window)
    return payload


# MIGRATIONS[n] upgrades a version-n payload to version n + 1.
MIGRATIONS: dict[int, Migration] = {1: _v1_to_v2, 2: _v2_to_v3, 3: _v3_to_v4, 4: _v4_to_v5, 5: _v5_to_v6, 6: _v6_to_v7}


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
