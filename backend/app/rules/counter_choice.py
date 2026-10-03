"""-- counters (wave 7C) -- "This creature enters with your choice of a flying counter or a first strike counter on it."

A replacement effect (614.1c, 614.12a): the choice is made as it enters, before it does, by its controller; the chosen
kind is put on it as it enters (122.6) like any "enters with" counter, through the counter choke point. A keyword
counter gives its keyword (122.1b, 613.1f). The choice travels like the other entering choices (``what``), here named
``counter kind: flying or first strike``.
"""

from __future__ import annotations

import re
from typing import Any

PREFIX = "counter kind: "
_CHOICE = re.compile(r"^~ enters with your choice of an? (?P<a>[a-z ]+?) counter or an? (?P<b>[a-z ]+?) counter on it\.$")


def parse(text: str) -> dict[str, Any] | None:
    """The replacement definition of the wording, or None (a kind that is no keyword counter is not read)."""
    from app.game.rules_state import KEYWORD_COUNTERS

    m = _CHOICE.match(text)
    if m is None or m["a"] == m["b"] or not {m["a"], m["b"]} <= KEYWORD_COUNTERS:
        return None
    return {"kind": "replacement", "replacement": "enters_choice", "counter_choice": [m["a"], m["b"]],
            "effects": [{"do": "choose_value", "what": f"{PREFIX}{m['a']} or {m['b']}"}]}


def options(what: str) -> list[str] | None:
    return what[len(PREFIX):].split(" or ") if what.startswith(PREFIX) else None


def entering(definitions: list[dict[str, Any]], choices: dict[str, str] | None) -> dict[str, int]:
    """The counter each chosen kind puts on the permanent entering (one of the kinds named, never another)."""
    out: dict[str, int] = {}
    for d in definitions:
        kinds = d.get("counter_choice") or ()
        kind = (choices or {}).get(f"{PREFIX}{' or '.join(kinds)}") if kinds else None
        if kind is not None and kind in kinds:
            out[kind] = out.get(kind, 0) + 1
    return out
