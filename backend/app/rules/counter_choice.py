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
_CHOICE = re.compile(r"^~ enters with your choice of (?P<kinds>.+) on it\.$")


def kinds_of(text: str) -> list[str] | None:
    """Only printed keyword-counter alternatives and the explicitly supported +1/+1 kind."""
    from app.game.rules_state import KEYWORD_COUNTERS

    parts = re.split(r",? or |, ", text)
    kinds = [re.sub(r" counters?$", "", re.sub(r"^(?:a|an) ", "", part)).strip() for part in parts]
    if len(kinds) < 2 or len(set(kinds)) != len(kinds) or not set(kinds) <= {*KEYWORD_COUNTERS, '+1/+1'}:
        return None
    return kinds


def parse(text: str) -> dict[str, Any] | None:
    """An entry replacement chooses one of its printed counter kinds before entering."""
    if text == "~ enters with your choice of two different counters on it from among menace, deathtouch, and lifelink.":
        pairs = ["menace + deathtouch", "menace + lifelink", "deathtouch + lifelink"]
        return {"kind": "replacement", "replacement": "enters_choice", "counter_choice": pairs,
                "counter_groups": {pair: pair.split(" + ") for pair in pairs},
                "effects": [{"do": "choose_value", "what": PREFIX + " or ".join(pairs)}]}
    m = _CHOICE.fullmatch(text)
    kinds = kinds_of(m['kinds']) if m is not None else None
    if kinds is None:
        return None
    return {"kind": "replacement", "replacement": "enters_choice", "counter_choice": kinds,
            "effects": [{"do": "choose_value", "what": PREFIX + ' or '.join(kinds)}]}


def options(what: str) -> list[str] | None:
    return what[len(PREFIX):].split(" or ") if what.startswith(PREFIX) else None


def entering(definitions: list[dict[str, Any]], choices: dict[str, str] | None) -> dict[str, int]:
    """The counter each chosen kind puts on the permanent entering (one of the kinds named, never another)."""
    out: dict[str, int] = {}
    for d in definitions:
        kinds = d.get("counter_choice") or ()
        kind = (choices or {}).get(f"{PREFIX}{' or '.join(kinds)}") if kinds else None
        if kind is not None and kind in kinds:
            for selected in d.get("counter_groups", {}).get(kind, [kind]):
                out[selected] = out.get(selected, 0) + 1
    return out
