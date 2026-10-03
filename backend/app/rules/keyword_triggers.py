"""Triggered keyword abilities read through their Comprehensive Rules definition (wave 6E).

A triggered keyword means a sentence the rules spell out (702.1); where the engine's trigger grammar already reads that
sentence, the keyword is carried out as it: battle cry (702.91a: "Whenever this creature attacks, each other attacking
creature gets +1/+0 until end of turn."), ingest (702.115a: "Whenever this creature deals combat damage to a player, that
player exiles the top card of their library."), poisonous N (702.70a), frenzy N (702.68a), afterlife N (702.135a). Each instance triggers
separately (702.91b, 702.115b, 702.70b, 702.68b): one definition per keyword piece of a line.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from app.rules.oracle import AbilityText

# keyword → its meaning (CR 2026-09-25), "{n}" standing for the keyword's number
MEANINGS: dict[str, str] = {
    "battle cry": "Whenever this creature attacks, each other attacking creature gets +1/+0 until end of turn.",  # 702.91a
    "ingest": "Whenever this creature deals combat damage to a player, that player exiles the top card of their library.",  # 702.115a
    "poisonous": "Whenever this creature deals combat damage to a player, that player gets {n} poison counters.",  # 702.70a
    "frenzy": "Whenever this creature attacks and isn't blocked, it gets +{n}/+0 until end of turn.",  # 702.68a
    # 702.101a ("you gain life equal to the total life lost this way": the grammar's "the life lost this way" is that
    # total, 119.3 — effects.lose_life binds what was actually lost)
    "extort": "Whenever you cast a spell, you may pay {{W/B}}. If you do, each opponent loses 1 life and you gain life equal "
              "to the life lost this way.",
    # 702.135a
    "afterlife": "When this permanent is put into a graveyard from the battlefield, create {n} 1/1 white and black Spirit "
                 "creature tokens with flying.",
}
_NUMBERED = frozenset({"poisonous", "frenzy", "afterlife"})


def pieces(kw: str, line: str) -> list[str]:
    """The pieces of a keyword line that are this keyword ("Flying, battle cry" → ["battle cry"])."""
    out = []
    for p in re.split(r"[,;]\s*", re.sub(r"\s*\(.*?\)", "", line).strip().rstrip(".")):
        p = p.strip().lower()
        if p == kw or (kw in _NUMBERED and re.fullmatch(rf"{re.escape(kw)} \d+", p)):
            out.append(p)
    return out


@lru_cache(maxsize=256)
def _definition(piece: str) -> str | None:
    from app.rules import scripts  # (scripts imports this module)
    from app.rules.characteristics import Characteristics

    kw, _, n = piece.rpartition(" ") if piece.split(" ")[-1].isdigit() else (piece, "", "")
    meaning = MEANINGS.get(kw)
    if meaning is None or (kw in _NUMBERED) != bool(n):
        return None
    ab = AbilityText(index=0, text=meaning.format(n=n), kind="triggered")
    d = scripts.define(ab, Characteristics(name="\u0000", abilities=(ab,), types=frozenset({"Creature"})))
    return json.dumps(d) if d is not None and d.get("kind") == "triggered" and scripts._event_refs_ok(d) else None


def definitions(kw: str, line: str) -> list[dict[str, Any]]:
    """The triggered abilities this keyword gives the line (one per instance), or [] when not read."""
    out = []
    for piece in pieces(kw, line):
        found = _definition(piece)
        if found is None:
            return []
        out.append(json.loads(found))
    return out


def supported(kw: str, line: str) -> bool:
    return kw in MEANINGS and bool(definitions(kw, line))
