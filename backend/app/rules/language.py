"""A small grammar for Oracle effect sentences: VERB + SUBJECT/OBJECT (selectors) + AMOUNT (value
expressions) + DESTINATION.

It's the fallback behind the literal templates in app/rules/scripts.py: one pattern per *verb*
(draw, gain/lose life, discard, mill, sacrifice, damage, destroy/exile/tap/untap, return, put and
remove counters, pump / grant until end of turn), each accepting any subject or object phrase
the selector grammar (app/rules/selectors.py) reads and any amount the value grammar
(app/rules/values.py) reads, including "for each …" and "where X is …".

``parse_sentence`` returns ``(effects, target key or None)`` or None when any part of the
sentence isn't understood (the card then stays manual: never a guess).
"""

from __future__ import annotations

import re
from typing import Any

from app.rules import selectors, values

Effects = list[dict[str, Any]]
AMT = values.AMOUNT
KEYWORDS = "|".join(k for k in selectors.KEYWORDS if k not in ("protection",))

# Legacy selector keys the rest of the engine already uses (targets.SELECTORS).
_LEGACY_TARGETS = {
    "any target": "any", "target player": "player", "target opponent": "opponent",
}
_PLAYER_GROUPS = {"you": "you", "each player": "each_player", "each opponent": "each_opponent",
                  "each of your opponents": "each_opponent"}


class _Fail(Exception):
    pass


def _target_key(phrase: str) -> str:
    if phrase in _LEGACY_TARGETS:
        return _LEGACY_TARGETS[phrase]
    m = re.match(r"^(another )?target (.+)$", phrase)
    if not m:
        raise _Fail
    sel = selectors.parse(("another " if m[1] else "") + m[2])
    if sel is None:
        raise _Fail
    return sel.key()


def ref(phrase: str) -> tuple[str, str]:
    """An object or player phrase → ("target", selector key) | ("each", selector key) |
    ("self", "") | ("players", "you" / "each_player" / "each_opponent")."""
    p = phrase.strip()
    if p in ("~", "it", "this creature", "this permanent"):
        return "self", ""
    if p in _PLAYER_GROUPS:
        return "players", _PLAYER_GROUPS[p]
    if p in _LEGACY_TARGETS or p.startswith(("target ", "another target ")):
        return "target", _target_key(p)
    m = re.match(r"^(?:each|all) (other )?(.+)$", p)
    if m:
        sel = selectors.parse(("other " if m[1] else "") + m[2])
        if sel is None:
            raise _Fail
        return "each", sel.key()
    if selectors.is_plural(p):  # "creatures you control get …", "other Elves you control …"
        sel = selectors.parse(p)
        if sel is not None and sel.player is None:
            return "each", sel.key()
    raise _Fail


def _who(kind: str, key: str) -> str:
    return {"target": "target", "self": "self", "players": key, "each": key}[kind]


def _amount(word: str) -> Any:
    v = values.parse_amount(word)
    if v is None:
        raise _Fail
    return v


def _with_rider(text: str) -> tuple[str, Any]:
    """Split "…, where X is the number of …" / "… for each …" off the sentence: the multiplier or
    the value of X (None if there's none)."""
    m = re.search(r",? where x is (.+)$", text)
    if m:
        v = values.parse_count(m[1])
        if v is None:
            raise _Fail
        return text[: m.start()], ("x", v)
    m = re.search(r" for each (.+)$", text)
    if m:
        v = values.parse_count(m[1])
        if v is None:
            raise _Fail
        return text[: m.start()], ("each", v)
    return text, None


def _apply(n: Any, rider: Any) -> Any:
    if rider is None:
        return n
    kind, v = rider
    if kind == "x":
        if n != {"x": 1}:
            raise _Fail  # "where X is" with no X in the sentence
        return v
    return v if n == 1 else {"times": [n, v]}


_SUBJ = r"(?:(?P<s>you|target player|target opponent|each player|each opponent|each of your opponents) )?"


def _subject(m: re.Match[str]) -> tuple[str, str | None]:
    """(who, target key)"""
    s = m["s"] or "you"
    if s in ("target player", "target opponent"):
        return "target", _LEGACY_TARGETS[s]
    return _PLAYER_GROUPS[s], None


def parse_sentence(text: str) -> tuple[Effects, str | None] | None:
    try:
        return _parse(text.strip())
    except _Fail:
        return None


def _parse(text: str) -> tuple[Effects, str | None]:
    text, rider = _with_rider(text)
    # -- players ------------------------------------------------------------------------------
    m = re.fullmatch(_SUBJ + rf"draws? (?P<n>{AMT}) cards?", text)
    if m:
        who, target = _subject(m)
        return [{"do": "draw", "who": who, "n": _apply(_amount(m["n"]), rider)}], target
    m = re.fullmatch(_SUBJ + rf"(?P<v>gains?|loses?) (?P<n>{AMT}) life", text)
    if m:
        who, target = _subject(m)
        verb = "gain_life" if m["v"].startswith("gain") else "lose_life"
        return [{"do": verb, "who": who, "n": _apply(_amount(m["n"]), rider)}], target
    m = re.fullmatch(_SUBJ + rf"(?P<v>discards?|mills?) (?P<n>{AMT}) cards?", text)
    if m:
        who, target = _subject(m)
        verb = "discard" if m["v"].startswith("discard") else "mill"
        return [{"do": verb, "who": who, "n": _apply(_amount(m["n"]), rider)}], target
    m = re.fullmatch(_SUBJ + rf"sacrifices? (?P<n>{AMT}) (?P<sel>.+)", text)
    if m and rider is None:
        who, target = _subject(m)
        sel = selectors.parse(m["sel"])
        if sel is None or sel.player is not None:
            raise _Fail
        return [{"do": "sacrifice_choice", "who": who, "sel": sel.key(), "n": _amount(m["n"])}], target
    # -- damage ---------------------------------------------------------------------------------
    m = re.fullmatch(rf"(?:~|it) deals (?P<n>{AMT}) damage to (?P<o>.+)", text)
    if m:
        n = _apply(_amount(m["n"]), rider)
        effects: Effects = []
        target = None
        for part in re.split(r" and (?=each |target |you$|any )", m["o"]):
            kind, key = ref(part)
            if kind == "target":
                if target is not None:
                    raise _Fail  # (two targets: app/rules/targets multi-target groups)
                target = key
            effects.append({"do": "damage", "who": _who(kind, key), "n": n})
        return effects, target
    if rider is not None and not text.startswith(("put ", "remove ")):
        raise _Fail
    # -- objects --------------------------------------------------------------------------------
    m = re.fullmatch(r"(?P<v>destroy|exile|tap|untap) (?P<o>.+)", text)
    if m:
        kind, key = ref(m["o"])
        if kind == "players":
            raise _Fail
        if kind == "each" and m["v"] == "destroy":
            return [{"do": "destroy", "who": key}], None
        return [{"do": m["v"], "who": _who(kind, key)}], key if kind == "target" else None
    m = re.fullmatch(r"return (?P<o>.+?) to (?P<d>its owner's hand|their owners' hands|their owner's hand|your hand|"
                     r"the battlefield(?P<t> tapped)?(?: under (?P<u>your|its owner's|their owners') control)?)", text)
    if m:
        kind, key = ref(m["o"])
        if kind in ("players", "self"):
            raise _Fail
        sel = selectors.from_key(key) if key.startswith(selectors.PREFIX) else None
        from_zone = sel is not None and sel.card
        who = _who(kind, key)
        target = key if kind == "target" else None
        if m["d"].startswith("the battlefield"):
            if not from_zone:
                raise _Fail  # (blink wordings are templated elsewhere)
            return [{"do": "return_card", "who": who, "to": "battlefield", "tapped": bool(m["t"]),
                     "under": "you" if m["u"] == "your" else "owner"}], target
        if from_zone:
            return [{"do": "return_card", "who": who, "to": "hand", "under": "you" if m["d"] == "your hand" else "owner"}], target
        if m["d"] == "your hand":
            raise _Fail
        return [{"do": "bounce", "who": who}], target
    m = re.fullmatch(rf"put (?P<n>{AMT}) (?P<k>\+1/\+1|-1/-1|[a-z]+) counters? on (?P<o>.+)", text)
    if m:
        kind, key = ref(m["o"])
        if kind == "players":
            raise _Fail
        return [{"do": "add_counters", "who": _who(kind, key), "kind": m["k"], "n": _apply(_amount(m["n"]), rider)}], \
            key if kind == "target" else None
    m = re.fullmatch(rf"remove (?P<n>{AMT}) (?P<k>\+1/\+1|-1/-1|[a-z]+) counters? from (?P<o>.+)", text)
    if m:
        kind, key = ref(m["o"])
        if kind == "players":
            raise _Fail
        return [{"do": "remove_counters", "who": _who(kind, key), "kind": m["k"], "n": _apply(_amount(m["n"]), rider)}], \
            key if kind == "target" else None
    m = re.fullmatch(rf"(?P<o>.+?) gets? (?P<p>[+\-−]\d+)/(?P<t>[+\-−]\d+)(?: and gains? (?P<kw>{KEYWORDS}))? until end of turn", text)
    if m:
        kind, key = ref(m["o"])
        if kind == "players":
            raise _Fail
        who = _who(kind, key)
        out: Effects = [{"do": "pump", "who": who, "p": _signed(m["p"]), "t": _signed(m["t"])}]
        if m["kw"]:
            out.append({"do": "grant", "who": who, "keywords": [m["kw"]]})
        return out, key if kind == "target" else None
    m = re.fullmatch(rf"(?P<o>.+?) gains? (?P<kw>{KEYWORDS}) until end of turn", text)
    if m:
        kind, key = ref(m["o"])
        if kind == "players":
            raise _Fail
        return [{"do": "grant", "who": _who(kind, key), "keywords": [m["kw"]]}], key if kind == "target" else None
    raise _Fail


def _signed(p: str) -> int:
    return -int(p[1:]) if p[0] in "-−" else int(p.lstrip("+"))
