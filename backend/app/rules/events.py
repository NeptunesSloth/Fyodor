"""Trigger conditions as data: "When/Whenever [subject] [event]" (CR 603.2, 603.6, 603.10).

A condition is a dict:

* ``event``: "enter" | "die" | "leave" | "attack" | "block" | "blocked" | "tapped" | "untapped" |
  "dealt_damage" | "deal_combat_damage_player" | "deal_damage_opponent" | "gain_life" | "lose_life" |
  "cast" | "draw" | "you_attack";
* ``subject``: "self" (this object), "self_or" (this object or another matching ``sel``), "sel"
  (any object matching ``sel``), or "player" (a player matching ``player``: "you" / "opponent" /
  "any");
* ``sel``: a selector key (app/rules/selectors.py); ``spell``: a selector key for cast spells;
* ``aggregate``: "one or more …" — one trigger per event batch, however many objects (603.2c);
* ``nth``: "your second card each turn" (the Nth such event this turn).

:func:`parse_condition` reads the wording; anything it doesn't read returns None (the ability
stays manual). Matching happens in app/rules/triggers.py against the event log.
"""

from __future__ import annotations

import re
from typing import Any

from app.rules import selectors

Condition = dict[str, Any]

_EVENT_VERBS = [
    (r"enters?", "enter"),
    (r"dies|die", "die"),
    (r"leaves? the battlefield", "leave"),
    (r"is put into a graveyard from the battlefield|are put into a graveyard from the battlefield", "die"),
    (r"attacks?", "attack"),
    (r"blocks?", "block"),
    (r"becomes? blocked", "blocked"),
    (r"becomes? tapped", "tapped"),
    (r"becomes? untapped", "untapped"),
    (r"(?:is|are) dealt damage", "dealt_damage"),
    (r"deals? combat damage to a player", "deal_combat_damage_player"),
    (r"deals? combat damage to an opponent", "deal_combat_damage_player"),
    (r"deals? damage to an opponent", "deal_damage_opponent"),
]
_PLAYER_VERBS = [
    (r"gains? life", "gain_life"),
    (r"loses? life", "lose_life"),
    (r"draws? a card", "draw"),
    (r"attacks?", "you_attack"),
]
_PLAYERS = {"you": "you", "an opponent": "opponent", "a player": "any", "each opponent": "opponent"}
_NTH = {"second": 2, "third": 3, "first": 1}


def parse_condition(cond: str) -> Condition | None:
    """The part between "When/Whenever" and the comma → a condition, or None."""
    c = cond.strip()
    m = re.fullmatch(r"~ (?P<a>enters|dies|attacks|leaves the battlefield) or (?P<b>enters|dies|attacks|leaves the battlefield)", c)
    if m:  # "When ~ enters or dies": one ability, each event (603.2)
        names = {"enters": "enter", "dies": "die", "attacks": "attack", "leaves the battlefield": "leave"}
        return {"event": "multi", "events": [names[m["a"]], names[m["b"]]]}
    # "you draw your second card each turn"
    m = re.fullmatch(r"(?P<p>you|an opponent|a player) draws? (?:their|your) (?P<nth>first|second|third) card each turn", c)
    if m:
        return {"event": "draw", "subject": "player", "player": _PLAYERS[m["p"]], "nth": _NTH[m["nth"]]}
    # "you cast a creature spell", "an opponent casts a spell", "a player casts a spell"
    m = re.fullmatch(r"(?P<p>you|an opponent|a player) casts? (?:an? )?(?P<spell>.+)", c)
    if m:
        spell = m["spell"]
        if spell.startswith("your ") or " each turn" in spell or "copy" in spell:
            return None
        sel = selectors.parse(spell) if spell != "spell" else selectors.Selector(zones=("stack",))
        if sel is None or sel.player is not None:
            return None
        return {"event": "cast", "subject": "player", "player": _PLAYERS[m["p"]],
                "spell": selectors.replace(sel, zones=("stack",)).key()}
    for pattern, event in _PLAYER_VERBS:
        m = re.fullmatch(rf"(?P<p>you|an opponent|a player|each opponent) (?:{pattern})", c)
        if m:
            return {"event": event, "subject": "player", "player": _PLAYERS[m["p"]]}
    for pattern, event in _EVENT_VERBS:
        m = re.fullmatch(rf"(?P<s>.+?) (?:{pattern})", c)
        if not m:
            continue
        subject = m["s"]
        if subject == "~":
            return {"event": event, "subject": "self"}
        m2 = re.fullmatch(r"~ or another (?P<rest>.+)", subject)
        if m2:
            sel = selectors.parse("another " + m2["rest"])
            if sel is None or sel.player is not None:
                return None
            return {"event": event, "subject": "self_or", "sel": sel.key()}
        aggregate = False
        m3 = re.fullmatch(r"one or more (?P<rest>.+)", subject)
        if m3:
            aggregate, subject = True, m3["rest"]
        else:
            m4 = re.fullmatch(r"(?:a|an|another) (?P<rest>.+)", subject)
            if not m4:
                return None
            subject = ("another " if subject.startswith("another ") else "") + m4["rest"]
        sel = selectors.parse(subject)
        if sel is None or sel.player is not None or sel.card:
            return None
        return {"event": event, "subject": "sel", "sel": sel.key(), "aggregate": aggregate}
    return None
