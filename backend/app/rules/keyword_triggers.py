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
    # -- keyword pieces (wave 8A) -- 702.43a: the triggered half of modular N (the static half, "enters with N +1/+1
    # counters", is replacements.entering_counters). The counters are those the permanent had as it left (113.6, LKI)
    "modular": "When this permanent is put into a graveyard from the battlefield, you may put a +1/+1 counter on target "
               "artifact creature for each +1/+1 counter on this permanent.",
    # -- keyword mechanics (wave 9D) -- 702.58a: the triggered half of graft N (the static half, "enters with N +1/+1 counters",
    # is replacements.entering_counters). 122.5: if either object has left the battlefield nothing is moved.
    "graft": "Whenever another creature enters, if this creature has a +1/+1 counter on it, you may move a +1/+1 counter "
             "from this creature onto that creature.",
    # -- keyword meanings (wave 11B) --
    "living weapon": "When this Equipment enters, create a 0/0 black Phyrexian Germ creature token, then attach this "
                     "Equipment to it.",  # 702.92a
    "for mirrodin!": "When this Equipment enters, create a 2/2 red Rebel creature token, then attach this Equipment to it.",  # 702.163a
    "annihilator": "Whenever this creature attacks, defending player sacrifices {n} permanents.",  # 702.86a
    "afflict": "Whenever this creature becomes blocked, defending player loses {n} life.",  # 702.130a
    # 702.156a: the triggered half of ravenous (its "enters with X +1/+1 counters" half is replacements.entering_counters;
    # X is 0 when it isn't cast, 107.3m)
    "ravenous": "When this permanent enters, if X is 5 or more, draw a card.",
    # -- keywords (wave 15E) --
    "training": "Whenever this creature and at least one other creature with power greater than this creature's power attack, "
                "put a +1/+1 counter on this creature.",  # 702.149a
    "dethrone": "Whenever this creature attacks the player with the most life or tied for most life, put a +1/+1 counter on "
                "this creature.",  # 702.105a
    "evolve": "Whenever a creature you control enters, if that creature's power is greater than this creature's power and/or "
              "that creature's toughness is greater than this creature's toughness, put a +1/+1 counter on this creature.",  # 702.100a
    # 702.181a ("those tokens enter tapped and attacking" written as the grammar reads it; "a" for one, {w} the number word)
    "mobilize": "Whenever this creature attacks, create {w} 1/1 red Warrior creature token{s} that{be} tapped and attacking. "
                "Sacrifice {them} at the beginning of the next end step.",
    # 702.63a vanishing N: enters with N time counters (replacements.entering_counters), and these two
    "vanishing": "At the beginning of your upkeep, if this permanent has a time counter on it, remove a time counter from it.\n"
                 "When the last time counter is removed from this permanent, sacrifice this permanent.",
    # 702.32a fading N: enters with N fade counters (replacements.entering_counters), and this
    "fading": "At the beginning of your upkeep, remove a fade counter from this permanent. If you can't, sacrifice this "
              "permanent.",
    "mentor": "Whenever this creature attacks, put a +1/+1 counter on target attacking creature with power less than this "
              "creature's power.",  # 702.134a
}
_NUMBERED = frozenset({"poisonous", "frenzy", "afterlife", "modular", "graft", "annihilator", "afflict", "mobilize", "vanishing", "fading", "backup"})


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
    """The definitions of one keyword piece as JSON: a list, one per ability the keyword is ("\n" in its meaning: vanishing is
    two triggered abilities, 702.63a)."""
    from app.rules import scripts  # (scripts imports this module)
    from app.rules.characteristics import Characteristics

    kw, _, n = piece.rpartition(" ") if piece.split(" ")[-1].isdigit() else (piece, "", "")
    meaning = MEANINGS.get(kw)
    if meaning is None or (kw in _NUMBERED) != bool(n):
        return None
    one = n == "1"
    word = "a" if one else {"2": "two", "3": "three", "4": "four", "5": "five"}.get(n, n)
    out = []
    for text in meaning.format(n=n, w=word, s="" if one else "s", be="'s" if one else " are",
                               them="it" if one else "them").split("\n"):
        ab = AbilityText(index=0, text=text, kind="triggered")
        d = scripts.define(ab, Characteristics(name="\u0000", abilities=(ab,), types=frozenset({"Creature"})))
        if d is None or d.get("kind") != "triggered" or not scripts._event_refs_ok(d):
            return None
        out.append(d)
    return json.dumps(out)


def definitions(kw: str, line: str) -> list[dict[str, Any]]:
    """The triggered abilities this keyword gives the line (every ability of each instance), or [] when not read."""
    out: list[dict[str, Any]] = []
    for piece in pieces(kw, line):
        found = _definition(piece)
        if found is None:
            return []
        out += json.loads(found)
    return out


def first_piece(kw: str, line: str, nth: int = 0) -> list[dict[str, Any]]:
    """The abilities of the ``nth`` instance of the keyword on the line (each instance is its own keyword ability)."""
    found = [_definition(p) for p in pieces(kw, line)[nth:nth + 1]]
    return json.loads(found[0]) if found and found[0] is not None else []


def supported(kw: str, line: str) -> bool:
    return kw in MEANINGS and bool(definitions(kw, line))


# -- keyword pieces (wave 8A) -- 702.124j: "Partner with [name]" is the commander pairing (app/rules/commander.py) and
# "When this permanent enters, target player may search their library for a card named [name], reveal it, put it into
# their hand, then shuffle."
_PARTNER_WITH = re.compile(r"partner with (?P<name>[^,.;()]+(?:, [^,.;()]+)?)", re.IGNORECASE)


def partner_with_name(line: str) -> str | None:
    m = _PARTNER_WITH.fullmatch(re.sub(r"\s*\(.*?\)", "", line).strip().rstrip("."))
    return m["name"].strip() if m else None


def partner_with_definition(line: str) -> dict[str, Any] | None:
    name = partner_with_name(line)
    if name is None:
        return None
    from app.rules import scripts
    from app.rules.characteristics import Characteristics

    text = f"Search your library for a card named {name}, reveal it, put it into your hand, then shuffle."
    ab = AbilityText(index=0, text=text, kind="spell")
    d = scripts.define(ab, Characteristics(name="\u0000", abilities=(ab,), types=frozenset({"Instant"})))
    if d is None or len(d.get("effects") or []) != 1 or d["effects"][0].get("do") != "search":
        return None
    return {"kind": "triggered", "trigger": "enters_self", "optional": False, "target": {"what": "player"},
            "effects": [{**d["effects"][0], "who": "target", "may": True}]}


# -- keywords (wave 15E) -- backup N (702.165a): "When this creature enters, put N +1/+1 counters on target creature. If that's
# another creature, it gains the following abilities until end of turn." The abilities are those written below the keyword
# on the card (keyword pieces and quoted abilities); each instance triggers separately (702.165b).
_COUNT_WORDS = {1: "a", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}


def backup_definition(ch: Any, ab: AbilityText, nth: int = 0) -> dict[str, Any] | None:
    """The triggered ability of the ``nth`` backup instance on ability line ``ab`` of ``ch``, or None when not read."""
    from app.rules import scripts
    from app.rules.characteristics import Characteristics

    found = pieces("backup", ab.text)
    following = [x for x in ch.abilities if x.index > ab.index]
    if nth >= len(found) or not following:
        return None
    n = int(found[nth].split()[1]) if " " in found[nth] else 0
    if n not in _COUNT_WORDS:
        return None
    keywords: list[str] = []
    quotes: list[str] = []
    for x in following:
        text = re.sub(r"\s*\(.*?\)", "", x.text).strip()
        if x.kind == "keywords":
            keywords += [p.strip().lower() for p in re.split(r"[,;]\s*", text.rstrip(".")) if p.strip()]
        elif '"' not in text:
            quotes.append(text)
        else:
            return None
    gains = [*keywords, *(f'"{q}"' for q in quotes)]
    if not gains:
        return None
    gained = ", ".join(gains[:-1]) + (", and " if len(gains) > 2 else " and ") + gains[-1] if len(gains) > 1 else gains[0]
    counters = f"{_COUNT_WORDS[n]} +1/+1 counter{'' if n == 1 else 's'}"
    text = (f"When this creature enters, put {counters} on target creature. If that's another creature, until end of turn, "
            f"it gains {gained}.")
    probe = AbilityText(index=0, text=text, kind="triggered")
    d = scripts.define(probe, Characteristics(name="\u0000", abilities=(probe,), types=frozenset({"Creature"})))
    return d if d is not None and d.get("kind") == "triggered" and scripts._event_refs_ok(d) else None
