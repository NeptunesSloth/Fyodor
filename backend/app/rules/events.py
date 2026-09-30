"""Trigger conditions as data: "When/Whenever [subject] [event]" (CR 603.2, 603.6, 603.10).

Researched against the Comprehensive Rules of 2026-09-25 (data/rules/comprehensive_rules/).

A condition is a dict:

* ``event``: "enter" | "die" | "leave" | "attack" | "block" | "blocked" | "tapped" | "untapped" |
  "dealt_damage" | "deal_combat_damage_player" | "deal_damage_opponent" | "deal_damage" |
  "gain_life" | "lose_life" | "cast" | "draw" | "you_attack" | "sacrifice" | "discard" | "cycle" |
  "create_token" | "counters_put" | "leave_graveyard" | "targeted" | "multi";
* ``subject``: "self" (this object), "self_or" (this object or another matching ``sel``), "sel"
  (any object matching ``sel``), "host" (the permanent this Aura / Equipment is attached to:
  "enchanted creature", "equipped creature"), or "player" (a player matching ``player``: "you" /
  "opponent" / "any");
* ``sel``: a selector key (app/rules/selectors.py); ``spell``: a selector key for cast spells;
  ``obj``: a selector key for the object a player acted on (the permanent sacrificed, the card
  discarded or cycled, the token created); ``other``: the creature on the other side of a block
  (509.3b "blocks a creature", 509.3d "becomes blocked by a creature");
* ``aggregate``: "one or more …" — one trigger per event batch, however many objects (603.2c);
* ``nth``: "your second card / spell each turn" (the Nth such event this turn);
* ``alone``: "attacks alone" (506.5: the only creature declared as an attacker);
* ``min_attackers``: "~ and at least two other creatures attack" (3), "you attack with three or
  more creatures" (3): how many creatures were declared as attackers;
* cast only: ``turn`` ("opponent": during an opponent's turn), ``from`` ("exile" | "graveyard" |
  "hand" | "not_hand": the zone the spell was cast from), ``targets`` ("self" or a selector key:
  a spell that targets it, 115.9b), ``kicked``;
* targeted only: ``by`` ("any" | "opponent" | "you": who controls the spell or ability), ``spell_only``
  (a spell, not an ability), ``first_each_turn`` ("for the first time each turn");
* counters_put only: ``counter`` (the kind, or None for any);
* deal_damage only: ``to`` ("any" | "player" | "opponent" | "creature" | "you"), ``combat`` (True: only
  combat damage, False: only noncombat damage, None: any);
* multi: ``events`` (each a trigger event of this object: "When ~ enters or dies", 603.2).

:func:`parse_condition` reads the wording; anything it doesn't read returns None (the ability
stays manual). Matching happens in app/rules/triggers.py against the event log.
"""

from __future__ import annotations

import re
from typing import Any

from app.rules import selectors

Condition = dict[str, Any]


class _Refuse(Exception):
    """A wording this grammar recognizes but doesn't model: the ability stays manual (never a guess)."""


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
# "~ deals [combat / noncombat] damage [to a creature / player / you]" (120.1, 510.2)
_DAMAGE_TO = {"": "any", " to a player": "player", " to a creature": "creature", " to an opponent": "opponent",
              " to you": "you", " to a player or planeswalker": None, " to a planeswalker": None}
_PLAYER_VERBS = [
    (r"gains? life", "gain_life"),
    (r"loses? life", "lose_life"),
    (r"draws? a card", "draw"),
    (r"attacks?", "you_attack"),
]
_PLAYERS = {"you": "you", "an opponent": "opponent", "a player": "any", "each opponent": "opponent"}
_NTH = {"second": 2, "third": 3, "first": 1, "fourth": 4, "fifth": 5}
_COUNT = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
_MULTI = {"enters": "enter", "dies": "die", "attacks": "attack", "leaves the battlefield": "leave", "blocks": "block",
          "becomes blocked": "blocked", "becomes tapped": "tapped", "becomes untapped": "untapped",
          "is dealt damage": "dealt_damage"}
_MULTI_RE = "|".join(sorted((re.escape(k) for k in _MULTI), key=len, reverse=True))
_P = r"(?P<p>you|an opponent|a player)"
# "enchanted creature", "equipped creature" …: the permanent the source is attached to (303.4, 301.5)
_HOSTS = ("enchanted creature", "equipped creature", "enchanted permanent", "enchanted land", "enchanted artifact")


def parse_condition(cond: str) -> Condition | None:
    """The part between "When/Whenever" and the comma → a condition, or None."""
    try:
        return _parse(cond.strip())
    except _Refuse:
        return None


def _object_sel(phrase: str, *, card: bool = False) -> str:
    """"a creature" / "another creature" / "a creature card" / "a token" → a selector key (the
    object an action was done to); ``card``: a card in a zone other than the battlefield."""
    p = re.sub(r"^(?:an?|one or more) ", "", phrase.strip())
    if p in ("card", "cards"):
        return selectors.Selector(card=True, zones=()).key()
    sel = _token_or_sel(p) if not card else selectors.parse(p)
    if sel is None or sel.player is not None or sel.card != card:
        raise _Refuse
    return sel.key()


def _count(word: str) -> int:
    if word.isdigit():
        return int(word)
    if word not in _COUNT:
        raise _Refuse
    return _COUNT[word]


def _parse(c: str) -> Condition | None:
    # "When ~ enters or dies", "Whenever ~ attacks or blocks": one ability, each event (603.2)
    m = re.fullmatch(rf"~ (?P<a>{_MULTI_RE}) or (?P<b>{_MULTI_RE})", c)
    if m:
        return {"event": "multi", "events": [_MULTI[m["a"]], _MULTI[m["b"]]]}
    # 509.3b / 509.3d: "~ blocks or becomes blocked by a creature" — once per creature on the other side
    m = re.fullmatch(r"~ (?P<v>blocks or becomes blocked by|blocks|becomes blocked by) (?P<o>an? .+|another .+)", c)
    if m:
        other = _object_sel(m["o"])
        events = {"blocks or becomes blocked by": ["block", "blocked"], "blocks": ["block"],
                  "becomes blocked by": ["blocked"]}[m["v"]]
        if len(events) == 1:
            return {"event": events[0], "subject": "self", "other": other}
        return {"event": "multi", "events": events, "other": other}
    # 506.5: "~ attacks alone", "a creature you control attacks alone"
    m = re.fullmatch(r"(?P<s>.+?) attacks alone", c)
    if m:
        base = _subject(m["s"])
        if base is None:
            return None
        return {**base, "event": "attack", "alone": True}
    # battalion: "~ and at least two other creatures attack" (the creatures declared as attackers)
    m = re.fullmatch(r"~ and at least (?P<n>\w+) other creatures attack", c)
    if m:
        return {"event": "attack", "subject": "self", "min_attackers": _count(m["n"]) + 1}
    # 508.3d / 508.3c: "you attack with one or more creatures", "you attack with three or more creatures"
    m = re.fullmatch(r"you attack with (?P<n>\w+) or more (?P<o>.+)", c)
    if m:
        sel = selectors.parse(m["o"])
        if sel is None or sel.player is not None or sel.card or not selectors.is_plural(m["o"]):
            return None
        return {"event": "you_attack", "subject": "player", "player": "you", "min_attackers": _count(m["n"]),
                "sel": sel.key()}
    # "you draw your second card each turn"
    m = re.fullmatch(rf"{_P} draws? (?:their|your) (?P<nth>first|second|third) card each turn", c)
    if m:
        return {"event": "draw", "subject": "player", "player": _PLAYERS[m["p"]], "nth": _NTH[m["nth"]]}
    found = _cast(c)
    if found is not None:
        return found
    found = _player_action(c)
    if found is not None:
        return found
    found = _object_event(c)
    if found is not None:
        return found
    for pattern, event in _PLAYER_VERBS:
        m = re.fullmatch(rf"(?P<p>you|an opponent|a player|each opponent) (?:{pattern})", c)
        if m:
            return {"event": event, "subject": "player", "player": _PLAYERS[m["p"]]}
    for pattern, event in _EVENT_VERBS:
        m = re.fullmatch(rf"(?P<s>.+?) (?:{pattern})", c)
        if not m:
            continue
        subject = m["s"]
        if subject in _HOSTS:
            # (after "dies" / "leaves", what was attached is found only looking back in time: not yet)
            return {"event": event, "subject": "host"} if event not in ("die", "leave") else None
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
        sel = _token_or_sel(subject)
        if sel is None or sel.player is not None or sel.card:
            return None
        return {"event": event, "subject": "sel", "sel": sel.key(), "aggregate": aggregate}
    return None


def _token_or_sel(phrase: str) -> selectors.Selector | None:
    """A subject phrase; "tokens you control" / "a creature token" name tokens (111.1)."""
    m = re.fullmatch(r"(?P<a>(?:another|other) )?(?P<rest>.*?)(?P<t>\btokens?)(?P<tail> .+)?", phrase)
    if m is None:
        return selectors.parse(phrase)
    base = selectors.parse(((m["a"] or "") + ((m["rest"] or "").strip() or ("permanents" if m["t"] == "tokens" else "permanent"))
                            + (m["tail"] or "")).strip())
    return selectors.replace(base, token=True) if base is not None else None


def _subject(s: str) -> Condition | None:
    """The subject of an object event: this object, or any object matching a selector."""
    if s == "~":
        return {"subject": "self"}
    m = re.fullmatch(r"(?:a|an|another) (?P<rest>.+)", s)
    if not m:
        return None
    sel = selectors.parse(("another " if s.startswith("another ") else "") + m["rest"])
    if sel is None or sel.player is not None or sel.card:
        return None
    return {"subject": "sel", "sel": sel.key(), "aggregate": False}


_FROM = {"from exile": "exile", "from your graveyard": "graveyard", "from a graveyard": "graveyard",
         "from anywhere other than your hand": "not_hand", "from your hand": "hand"}


def _cast(c: str) -> Condition | None:
    """601.2i: "you cast a creature spell", "an opponent casts a spell", "you cast your second spell
    each turn", "you cast a spell that targets ~" (heroic), "you cast a spell from exile", "you
    cast a kicked spell", "you cast a spell during an opponent's turn"."""
    m = re.fullmatch(rf"{_P} casts? (?P<spell>.+)", c)
    if not m:
        return None
    out: Condition = {"event": "cast", "subject": "player", "player": _PLAYERS[m["p"]]}
    spell = m["spell"]
    t = re.fullmatch(r"(?P<rest>.+?) during (?:an|each) opponent's turn", spell)
    if t:
        out["turn"] = "opponent"
        spell = t["rest"]
    nth = re.fullmatch(r"(?:your|their) (?P<nth>first|second|third|fourth|fifth) spell(?P<each> each turn)?", spell)
    if nth and (nth["each"] or out.get("turn")):  # (the Nth spell of any kind: counted per player per turn)
        return {**out, "nth": _NTH[nth["nth"]], "spell": selectors.Selector(zones=("stack",)).key()}
    if spell.startswith(("your ", "their ")) or " each turn" in spell or "copy" in spell or " this turn" in spell:
        return None
    f = re.fullmatch(r"(?P<rest>.+?) (?P<from>from exile|from your graveyard|from a graveyard|"
                     r"from anywhere other than your hand|from your hand)", spell)
    if f:
        out["from"] = _FROM[f["from"]]
        spell = f["rest"]
    tg = re.fullmatch(r"(?P<rest>.+?) that targets (?P<t>~|an? .+|one or more .+)", spell)
    if tg:
        if tg["t"] == "~":
            out["targets"] = "self"
        else:
            sel = selectors.parse(re.sub(r"^(?:an?|one or more) ", "", tg["t"]))
            if sel is None or sel.player is not None or sel.card:
                return None
            out["targets"] = sel.key()
        spell = tg["rest"]
    k = re.fullmatch(r"an? kicked (?P<rest>.+)", spell)
    if k:
        out["kicked"] = True
        spell = "a " + k["rest"]
    spell = re.sub(r"^an? ", "", spell)
    sel = selectors.parse(spell) if spell != "spell" else selectors.Selector(zones=("stack",))
    if sel is None or sel.player is not None:
        return None
    return {**out, "spell": selectors.replace(sel, zones=("stack",)).key()}


def _player_action(c: str) -> Condition | None:
    """A player sacrifices (701.21), discards (701.9), cycles (702.29) or creates a token (111.2)."""
    m = re.fullmatch(rf"{_P} (?P<v>sacrifices?|discards?|cycles? or discards?|cycles?|creates?) (?P<o>.+)", c)
    if not m:
        return None
    v = m["v"]
    if " or " in v:  # 702.29d: "cycles or discards" triggers once for a cycled card — it was discarded (702.29a)
        event = "discard"
    else:
        event = next(e for w, e in (("sacrifice", "sacrifice"), ("discard", "discard"), ("cycle", "cycle"),
                                    ("create", "create_token")) if v.startswith(w))
    o = m["o"]
    if o in ("~", "this card") and event in ("sacrifice", "cycle") and m["p"] == "you":
        # "When you sacrifice ~" (603.10a: looks back in time), "When you cycle ~" (702.29c: from
        # whatever zone the card went to)
        return {"event": event, "subject": "self"}
    aggregate = o.startswith("one or more ")
    if event == "create_token" and not re.search(r"\btokens?$", o):
        return None
    if not re.match(r"^(?:an?|one or more|another) ", o):
        return None
    card = event in ("discard", "cycle")
    return {"event": event, "subject": "player", "player": _PLAYERS[m["p"]], "obj": _object_sel(o, card=card),
            "aggregate": aggregate}


def _object_event(c: str) -> Condition | None:
    """Object events beyond the basic verbs: counters put on (122.6), leaving a graveyard (603.10a),
    becoming the target of a spell or ability (115.9, 603.2e), dealing damage (120.1)."""
    # "one or more +1/+1 counters are put on ~", "a +1/+1 counter is put on a creature you control"
    m = re.fullmatch(r"(?:one or more|an?) (?:(?P<k>\+1/\+1|-1/-1|[a-z]+) )?counters? (?:is|are) put on (?P<s>.+)", c)
    if m:
        base = _subject(m["s"])
        if base is None:
            raise _Refuse
        return {**base, "event": "counters_put", "counter": m["k"]}
    # "one or more creature cards leave your graveyard", "a card leaves your graveyard"
    m = re.fullmatch(r"(?P<o>(?:one or more|an?) .+?) leaves? your graveyard", c)
    if m:
        sel = selectors.from_key(_object_sel(m["o"], card=True))
        return {"event": "leave_graveyard", "subject": "sel", "sel": selectors.replace(sel, zone_owner="you").key(),
                "aggregate": m["o"].startswith("one or more ")}
    # "~ becomes the target of a spell or ability an opponent controls [for the first time each turn]"
    m = re.fullmatch(r"(?P<s>.+?) becomes the target of (?P<what>a spell or ability|a spell)"
                     r"(?: (?P<by>an opponent controls|you control))?(?P<first> for the first time each turn)?", c)
    if m:
        base = _subject(m["s"])
        if base is None:
            raise _Refuse
        return {**base, "event": "targeted", "by": {"an opponent controls": "opponent", "you control": "you"}.get(m["by"] or "", "any"),
                "spell_only": m["what"] == "a spell", "first_each_turn": bool(m["first"])}
    # "~ deals damage", "~ deals combat damage to a creature", "~ deals noncombat damage to a player"
    m = re.fullmatch(r"(?P<s>.+?) deals (?P<c>combat |noncombat )?damage(?P<to>| to a player| to a creature| to an opponent|"
                     r" to you| to a player or planeswalker| to a planeswalker)", c)
    # (combat damage to a player / an opponent and damage to an opponent: the verbs below)
    if m and not (m["to"] == " to an opponent" and m["c"] != "noncombat ") and \
            not (m["to"] == " to a player" and m["c"] == "combat "):
        to = _DAMAGE_TO[m["to"]]
        if to is None:
            raise _Refuse
        if m["s"] in _HOSTS:
            who: Condition | None = {"subject": "host"}
        else:
            who = _subject(m["s"])
        if who is None:
            return None
        return {**who, "event": "deal_damage", "to": to,
                "combat": {"combat ": True, "noncombat ": False}.get(m["c"] or "")}
    return None
