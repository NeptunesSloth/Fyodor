"""Keyword help: a short plain-English line for each keyword and ability word in the card database, for the dotted-underline
tooltips in card text (frontend cards/keywordTip.ts). Read from the cards' own reminder text (the most common wording, with costs
and counts made generic), and for an ability word from what its abilities usually start with. Offline: only the local database."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Any

# What the cards don't spell out (no reminder text in the database, or newer than it): the engine's own wording.
OVERRIDES = {
    "dive": "It can't be blocked until it deals combat damage while attacking.",
    "rulebreaker": "Ability word: this commander bends a deckbuilding rule; the card says which.",
    "scry": "Look at the top N cards of your library, then put any number of them on the bottom and the rest on top in any order.",
    "protection": "It can't be blocked, targeted, dealt damage, enchanted or equipped by anything with the named quality.",
    "enchant": "An Aura: you target what it will enchant as you cast it, and it enters attached to that.",
    "partner with": "You can have two commanders if they partner with each other. When it enters, target player may search for the other.",
    "transform": "Turn it over to its other face. It stays the same object.",
    "fight": "Each deals damage equal to its power to the other.",
    "goad": "Until your next turn, it attacks each combat if able, and attacks a player other than you if able.",
    "explore": "Reveal the top card of your library. If it's a land, put it into your hand; otherwise put a +1/+1 counter on this creature, then you may put the card into your graveyard.",
    "connive": "Draw a card, then discard a card. If you discarded a nonland card, put a +1/+1 counter on this creature.",
    "landcycling": "[cost], Discard this card: Search your library for a land card of the named type, reveal it, put it into your hand, then shuffle.",
    "typecycling": "[cost], Discard this card: Search your library for a card of the named type, reveal it, put it into your hand, then shuffle.",
    "indestructible": "Effects that say \"destroy\" don't destroy it, and lethal damage doesn't either.",
}
# Token kinds Scryfall lists among a card's keywords: names, not abilities (their text is on the token).
SKIP = frozenset({"food", "treasure", "clue", "blood", "map", "powerstone", "incubator", "role token", "gold", "shard", "junk", "double"})
_COST = re.compile(r"(?:\{[^}]+\})+")
_TAP = {"{T}": "tap", "{Q}": "untap"}
_COUNT = re.compile(r"(?<![/\d+-])\b(?:\d+\b(?![/\d])|(?:two|three|four|five|six|seven|eight|nine|ten)(?= cards?\b))")
MAX_LEN = 220


def _generic(text: str) -> str:
    text = _COST.sub(lambda m: _TAP.get(m.group(0), "[cost]"), text)
    return _COUNT.sub("N", text).strip()


def build(rows: Iterable[tuple[str, str | None, str | None]]) -> dict[str, str]:
    """{lowercase term: line} from (keywords JSON, oracle text, faces JSON) rows, one per card."""
    reminders: dict[str, Counter[str]] = defaultdict(Counter)
    openers: dict[str, Counter[str]] = defaultdict(Counter)
    for keywords, oracle, faces in rows:
        kws = json.loads(keywords or "[]")
        if not kws:
            continue
        texts = [oracle or ""] + [f.get("oracle_text") or "" for f in json.loads(faces or "null") or []]
        lines = [line for text in texts for line in text.split("\n")]
        for kw in kws:
            if kw.lower() in SKIP:
                continue
            head = re.escape(kw)
            for line in lines:
                if m := re.match(rf"{head}(?:[ —-][^(.\n]{{0,30}})?\.? ?\(([^)]+)\)", line, re.I):
                    reminders[kw.lower()][_generic(m.group(1))] += 1
                elif m := re.match(rf"{head} — ([^,.]+)", line):
                    openers[kw.lower()][m.group(1)] += 1
    out: dict[str, str] = {}
    for term, seen in openers.items():
        out[term] = f"Ability word (no rules meaning of its own). Usually: “{seen.most_common(1)[0][0]}, …”"
    for term, seen in reminders.items():
        out[term] = seen.most_common(1)[0][0]
    out.update(OVERRIDES)
    return {t: v if len(v) <= MAX_LEN else v[: MAX_LEN - 1].rstrip() + "…" for t, v in out.items()}


def from_connection(conn: Any) -> dict[str, str]:
    rows = conn.execute(
        "SELECT p.keywords, p.oracle_text, p.card_faces FROM oracle_defaults d JOIN printings p ON p.id = d.printing_id"
        " WHERE d.is_token = 0"
    ).fetchall()
    return build((r[0], r[1], r[2]) for r in rows)
