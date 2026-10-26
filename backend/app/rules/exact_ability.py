"""Shared tail of the wave 110 exact-wording tables: an ability whose whole text is a table key is read as the native wording the table gives, then
the table's patch function is applied to that definition (or, for a ``same`` table, the native definition is used as it is).

The re-entry guard (from wave 110M): while a key is being read natively, the same key from the same table reads as "no entry", so a native wording
that is itself a key of its table falls through to the grammar instead of recursing.
"""
from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any


class _Reading(threading.local):
    def __init__(self) -> None:
        self.keys: set[tuple[int, str]] = set()


_READING = _Reading()  # the (table, text) pairs being read natively right now, per thread


def build(ability: Any, ch: Any, table: Mapping[str, tuple[str, Callable[[dict[str, Any]], dict[str, Any]]]],
          same: Mapping[str, str] | None = None) -> dict[str, Any] | None:
    from app.rules import scripts

    text = ability.text.strip()
    if same is not None and (native_text := same.get(text)) is not None:
        return scripts.define(replace(ability, text=native_text), ch)
    key = (id(table), text)
    if (built := table.get(text)) is None or key in _READING.keys:
        return None
    _READING.keys.add(key)
    try:
        native = scripts.define(replace(ability, text=built[0]), ch)
    finally:
        _READING.keys.discard(key)
    return None if native is None else built[1](native)
