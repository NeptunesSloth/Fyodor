"""A small grammar for Oracle effect sentences: VERB + SUBJECT/OBJECT (selectors) + AMOUNT (value
expressions) + DESTINATION.

It's the fallback behind the literal templates in app/rules/scripts.py: one pattern per *verb*
(draw, gain/lose life, discard, mill, sacrifice, damage, destroy/exile/tap/untap, return, put and
remove counters, pump / grant until end of turn), each accepting any subject or object phrase
the selector grammar (app/rules/selectors.py) reads and any amount the value grammar
(app/rules/values.py) reads, including "for each …" and "where X is …".

``parse_sentence`` returns ``(effects, targets)`` or None when any part of the sentence isn't
understood (the card then stays manual: never a guess). ``targets`` is None, a selector key (one
"target [something]" with one target), or target group(s) (CR 115.1, 601.2c): a dict or a list
of dicts ``{"what": key, "min": n, "max": n, "divide": …, "another": key}`` for "up to two target
creatures", "one or two targets", "target creature and target artifact" (two groups: two
instances of the word "target", 115.3), "N damage divided as you choose among …" (601.2d).
Effects name a group with "target" (the sentence's first) or "target:<k>" (its k-th); "it" and
"them" are pronouns, resolved against the ability's groups by scripts.resolve_it.
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
                  "each of your opponents": "each_opponent", "that player": "event_player"}


class _Fail(Exception):
    pass


MAX_TARGETS = 20  # "any number of target …": at most this many (the intents' limit)
_QTY = r"one|two|three|four|five|six|seven|eight|nine|ten|\d+"
_GROUP = re.compile(rf"^(?:each of )?(?:up to (?P<upto>{_QTY})|(?P<range>one or two|one, two, or three)|"
                    rf"(?P<any>any number of)|(?P<n>{_QTY})) (?P<rest>targets|target .+)$")


def _qty(word: str) -> int:
    return int(word) if word.isdigit() else values.NUMBERS[word]


def simple(group: dict[str, Any]) -> bool:
    """One "target [something]" with exactly one target: what definitions write as "target"."""
    return (group["min"], group["max"]) == (1, 1) and not ({"divide", "another", "distinct_from", "same_graveyard"} & set(group))


def target_group(phrase: str) -> dict[str, Any] | None:
    """A target phrase → a target group (115.1; 601.2c: the number of targets): "target creature"
    (1), "up to two target creatures" (0-2), "two target creatures" (2), "one or two targets"
    (1-2), "any number of target creatures" (0-MAX_TARGETS). "another target creature" also
    carries "another": its selector without "another" (scripts: when an earlier target of the
    same ability exists, "another" means distinct from it). None if it isn't a target phrase."""
    p = phrase.strip()
    if p in _LEGACY_TARGETS:
        return {"what": _LEGACY_TARGETS[p], "min": 1, "max": 1}
    if p == "another target":  # 115.4 (Arc Trail): any target other than the earlier one
        return {"what": "", "min": 1, "max": 1, "another": "any"}
    if p.startswith(("target ", "another target ")):
        what, _ = _group_constraints(_target_key(p))  # (one target: "a single graveyard" is vacuous)
        group: dict[str, Any] = {"what": what, "min": 1, "max": 1}
        if p.startswith("another "):
            group["another"] = _group_constraints(_target_key(p[len("another "):]))[0]
        return group
    m = _GROUP.match(p)
    if not m:
        return None
    what, constraints = ("any", {}) if m["rest"] == "targets" else _group_constraints(_target_key(m["rest"]))
    if m["upto"]:
        lo, hi = 0, _qty(m["upto"])
    elif m["range"]:
        lo, hi = 1, 2 if m["range"] == "one or two" else 3
    elif m["any"]:
        lo, hi = 0, MAX_TARGETS
    else:
        lo = hi = _qty(m["n"])
    if not 1 <= hi <= MAX_TARGETS:
        raise _Fail
    if hi > 1 and re.search(r"\ban opponent(?:'s)?\b", m["rest"]):
        raise _Fail  # "two target cards from an opponent's graveyard": the same opponent? (not a guess)
    if hi > 1 and what.startswith(selectors.PREFIX) and selectors.from_key(what).controller == "defending":
        raise _Fail  # "two target creatures defending player controls": one specific defending player (508.5a)
    return {"what": what, "min": lo, "max": hi, **constraints}


def _group_constraints(key: str) -> tuple[str, dict[str, Any]]:
    """A selector key → (the key without group-level constraints, those constraints): "from a
    single graveyard" is a constraint on the targets together (all from one graveyard — one
    owner, 400.1), not on each card: ``{"same_graveyard": True}`` (checked by targets.choose_groups)."""
    if not key.startswith(selectors.PREFIX):
        return key, {}
    sel = selectors.from_key(key)
    if "single_graveyard" not in sel.extras:
        return key, {}
    plain = selectors.replace(sel, extras=tuple(x for x in sel.extras if x != "single_graveyard"))
    return plain.key(), {"same_graveyard": True}


def _out(groups: list[dict[str, Any]]) -> Any:
    """A sentence's targets as parse_sentence returns them: None, a plain selector key (one
    simple target, as before multi-target groups), one group, or a list of groups."""
    if not groups:
        return None
    if len(groups) == 1:
        return groups[0]["what"] if simple(groups[0]) else groups[0]
    return groups


def _divided(phrase: str, what: str, total: Any) -> dict[str, Any]:
    """601.2d: "… divided as you choose among one, two, or three targets" / "distribute N
    counters among …": each target gets at least one, so at least one target and at most
    ``total`` of them."""
    group = target_group(phrase)
    if group is None or "another" in group or not (isinstance(total, int) or total == {"x": 1}):
        raise _Fail
    group = {**group, "min": max(1, group["min"]), "divide": {"what": what, "total": total}}
    if isinstance(total, int):
        if total < 1:
            raise _Fail
        group["max"] = min(group["max"], total)
    return group


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


_THEM = ("them", "each of them", "they", "those creatures", "those permanents", "those cards")


def ref(phrase: str) -> tuple[str, str, dict[str, Any] | None]:
    """An object or player phrase → ("target", selector key, target group) | ("each", selector
    key, None) | ("self", "", None) | ("players", "you" / "each_player" / "each_opponent", None) |
    a pronoun ("it" / "them")."""
    p = phrase.strip()
    if p in ("~", "this creature", "this permanent"):
        return "self", "", None
    if p in ("it", "that creature", "that permanent"):
        return "it", "", None  # a pronoun: resolved against its antecedent (scripts.resolve_it)
    if p in _THEM:
        return "them", "", None  # the targets just named (scripts.resolve_it)
    if p in ("enchanted creature", "equipped creature", "enchanted permanent", "enchanted land", "enchanted artifact"):
        return "host", "", None  # what the source Aura / Equipment is attached to
    if p in _PLAYER_GROUPS:
        return "players", _PLAYER_GROUPS[p], None
    group = target_group(p)
    if group is not None:
        return "target", group["what"], group
    m = re.match(r"^(?:each|all) (other )?(.+)$", p)
    if m:
        sel = selectors.parse(("other " if m[1] else "") + m[2])
        if sel is None or _untargeted_defending(sel):
            raise _Fail
        return "each", sel.key(), None
    if selectors.is_plural(p):  # "creatures you control get …", "other Elves you control …"
        sel = selectors.parse(p)
        if sel is not None and sel.player is None and not _untargeted_defending(sel):
            return "each", sel.key(), None
    raise _Fail


def _untargeted_defending(sel: selectors.Selector) -> bool:
    """"Creatures defending player controls get -1/-1": not targeted, so nobody picks which
    defending player it is; that's the player the triggering attacker is attacking (508.5), which
    may not be the ability's source ("Whenever a Dragon you control attacks, …") — the selector
    only knows the source, so a non-targeted "defending player" could hit the wrong player's
    creatures in a multiplayer game: manual. Targeted forms are fine: the chooser picks one
    defending player's permanent (508.5a)."""
    return sel.controller == "defending"


def _who(kind: str, key: str) -> str:
    return {"target": "target", "self": "self", "it": "it", "them": "them", "host": "host", "players": key,
            "each": key}[kind]


# "… and target artifact", "… and up to one target creature", "… and another target creature"
_AND_TARGET = r" and (?=(?:each of )?(?:another |up to \w+ |any number of |one or two |two |three )?targets?\b|any target)"


def _objects(o: str) -> tuple[list[str], list[dict[str, Any]]]:
    """"target creature and target artifact" → (who per part, target groups): each "target" is
    its own group (115.3), named "target" (the first) / "target:<k>"."""
    whos: list[str] = []
    groups: list[dict[str, Any]] = []
    for part in re.split(_AND_TARGET, o):
        kind, key, group = ref(part)
        if group is not None:
            whos.append("target" if not groups else f"target:{len(groups)}")
            groups.append(group)
        else:
            whos.append(_who(kind, key))
    return whos, groups


RESTRICTIONS = {"block": ["cant_block"], "attack": ["cant_attack"], "attack or block": ["cant_attack_or_block"],
                "be blocked": ["cant_be_blocked"]}


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


_SUBJ = r"(?:(?P<s>you|target player|target opponent|each player|each opponent|each of your opponents|that player) )?"


def _subject(m: re.Match[str]) -> tuple[str, str | None]:
    """(who, target key)"""
    if m["s"] is None and re.match(r"^\w+s\b", m.string):
        raise _Fail  # "discards a card" with no subject: someone else's (the lead's subject), not "you"
    s = m["s"] or "you"
    if s in ("target player", "target opponent"):
        return "target", _LEGACY_TARGETS[s]
    return _PLAYER_GROUPS[s], None


_SEARCH = re.compile(
    rf"search your library for (?:(?P<upto>up to) )?(?P<n>{AMT}) (?P<sel>.+?), "
    r"(?:(?P<reveal>reveal (?:it|them|that card|those cards)), )?"
    r"(?:(?:put (?:it|them|that card|those cards) (?P<dest>into your hand|onto the battlefield tapped|onto the battlefield|"
    r"into your graveyard)|(?P<exile>exile (?:it|them|that card))), then shuffle"
    r"|then shuffle and put (?:that card|it) on top)")
_DESTS = {"into your hand": "hand", "onto the battlefield tapped": "battlefield_tapped", "onto the battlefield": "battlefield",
          "into your graveyard": "graveyard"}


def _search(text: str) -> tuple[Effects, str | None] | None:
    """701.19: "Search your library for [up to N] [card selector], [reveal it,] put it [where], then
    shuffle" (or "…, reveal it, then shuffle and put that card on top")."""
    m = _SEARCH.fullmatch(text)
    if not m:
        return None
    sel = selectors.parse(m["sel"])
    if sel is None or sel.player is not None or (not sel.card and m["sel"] not in ("a plains", "an island")):
        raise _Fail
    sel = selectors.replace(sel, zones=("library",), zone_owner="you", card=True)
    n = _amount(m["n"])
    to = "top" if m["dest"] is None and m["exile"] is None else ("exile" if m["exile"] else _DESTS[m["dest"]])
    return [{"do": "search", "who": "you", "sel": sel.key(), "label": m["sel"], "max": n,
             "to": to, "reveal": bool(m["reveal"]), "upto": bool(m["upto"])}], None  # (only when the text says so: 701.23e)


_REST = r"(?:the rest|the other|the others) (?P<rest>into your graveyard|on the bottom of your library(?: in (?:any|a random) order)?)"
_TOP = re.compile(rf"look at the top (?:(?P<n>{AMT}) cards|card) of your library")
_PICK = re.compile(
    rf"(?:(?P<may>you may reveal) |put )(?P<q>up to {AMT}|any number of|{AMT}) (?:of them|(?P<sel>.+?) from among them)"
    r"(?: and put (?:it|them|the revealed cards|that card|those cards))?"
    r" (?P<to>into your hand|onto the battlefield tapped|onto the battlefield)"
    rf"(?: and {_REST})?")
_REST_ALONE = re.compile(rf"put {_REST}")


def _rest(where: str) -> dict[str, Any]:
    to = "graveyard" if where == "into your graveyard" else "bottom_random" if "random" in where else "bottom_any"
    return {"do": "rest_looked", "to": to}


def _looking(text: str) -> tuple[Effects, str | None] | None:
    """701.xx "look at the top N cards of your library" and what follows ("put one of them into
    your hand and the rest on the bottom …", "you may reveal a creature card from among them …")."""
    m = _TOP.fullmatch(text)
    if m:
        return [{"do": "look_top", "n": _amount(m["n"]) if m["n"] else 1}], None
    m = _PICK.fullmatch(text)
    if m:
        q = m["q"]
        optional = bool(m["may"]) or q.startswith(("up to", "any number"))
        n: Any = 99 if q == "any number of" else _amount(q[6:] if q.startswith("up to ") else q)
        sel = None
        if m["sel"]:
            parsed = selectors.parse(m["sel"])
            if parsed is None or parsed.player is not None:
                raise _Fail
            sel = parsed.key()
        to = {"into your hand": "hand", "onto the battlefield tapped": "battlefield_tapped",
              "onto the battlefield": "battlefield"}[m["to"]]
        out: Effects = [{"do": "pick_looked", "n": n, "sel": sel, "to": to, "optional": optional, "reveal": bool(m["may"])}]
        if m["rest"]:
            out.append(_rest(m["rest"]))
        return out, None
    m = _REST_ALONE.fullmatch(text)
    if m:
        return [_rest(m["rest"])], None
    return None


def parse_sentence(text: str) -> tuple[Effects, Any] | None:
    try:
        return _parse(text.strip())
    except _Fail:
        return None


def _one(group: dict[str, Any] | None) -> Any:
    return _out([group] if group is not None else [])


def _parse(text: str) -> tuple[Effects, Any]:
    found = _search(text) or _looking(text)
    if found is not None:
        return found
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
    src: dict[str, Any] = {"src": "it"} if text.startswith("it ") else {}
    m = re.fullmatch(rf"(?P<src>~|it) deals (?P<n>{AMT}) damage divided as you choose among (?P<o>.+)", text)
    if m:  # 601.2d: the division is announced as the spell is cast (each target gets at least 1)
        if rider is not None:
            raise _Fail
        return [{"do": "damage", "who": "target", "n": {"divided": 0}, **src}], _divided(m["o"], "damage", _amount(m["n"]))
    m = re.fullmatch(rf"(?P<src>~|it) deals (?P<n>{AMT}) damage to (?P<o1>.+?) and (?P<m>{AMT}) damage to (?P<o2>.+)", text)
    if m and rider is None:  # "… 2 damage to any target and 1 damage to another target" (two groups)
        effects: Effects = []
        groups: list[dict[str, Any]] = []
        for o, n in ((m["o1"], m["n"]), (m["o2"], m["m"])):
            whos, parts = _objects(o)
            if len(whos) != 1:
                raise _Fail
            effects.append({"do": "damage", "who": whos[0] if not parts else ("target" if not groups else f"target:{len(groups)}"),
                            "n": _amount(n), **src})
            groups += parts
        return effects, _out(groups)
    m = re.fullmatch(rf"(?P<src>~|it) deals (?P<n>{AMT}) damage to (?P<o>.+)", text)
    if m:
        n = _apply(_amount(m["n"]), rider)
        effects = []
        groups = []
        for part in re.split(r" and (?=each |you$)|" + _AND_TARGET, m["o"]):
            kind, key, group = ref(part)
            who = _who(kind, key)
            if group is not None:
                who = "target" if not groups else f"target:{len(groups)}"
                groups.append(group)
            effects.append({"do": "damage", "who": who, "n": n, **src})
        return effects, _out(groups)
    if rider is not None and not text.startswith(("put ", "remove ")):
        raise _Fail
    # -- objects --------------------------------------------------------------------------------
    m = re.fullmatch(r"(?P<v>destroy|exile|tap|untap) (?P<o>.+)", text)
    if m:
        whos, groups = _objects(m["o"])
        if len(whos) > 1:  # "destroy target artifact and target enchantment": one group each (115.3)
            if len(groups) != len(whos):
                raise _Fail
            return [{"do": m["v"], "who": w} for w in whos], _out(groups)
        kind, key, group = ref(m["o"])
        if kind == "players":
            raise _Fail
        if kind == "each" and m["v"] == "destroy":
            return [{"do": "destroy", "who": key}], None
        return [{"do": m["v"], "who": _who(kind, key)}], _one(group)
    m = re.fullmatch(r"(?P<o>.+?) can't (?P<r>attack or block|block|attack|be blocked) this turn", text)
    if m:
        kind, key, group = ref(m["o"])
        if kind == "players":
            raise _Fail
        return [{"do": "restrict", "who": _who(kind, key), "rules": RESTRICTIONS[m["r"]]}], _one(group)
    if text in ("return ~ to its owner's hand", "return it to its owner's hand"):
        return [{"do": "bounce", "who": "self" if text.startswith("return ~") else "it"}], None
    m = re.fullmatch(r"return (?P<o>.+?) to (?P<d>its owner's hand|their owners' hands|their owner's hand|your hand|"
                     r"the battlefield(?P<t> tapped)?(?: under (?P<u>your|its owner's|their owners') control)?)", text)
    if m:
        kind, key, group = ref(m["o"])
        if kind in ("players", "self", "it", "them"):
            raise _Fail
        sel = selectors.from_key(key) if key.startswith(selectors.PREFIX) else None
        from_zone = sel is not None and sel.card
        who = _who(kind, key)
        target = _one(group)
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
    m = re.fullmatch(rf"distribute (?P<n>{AMT}) (?P<k>\+1/\+1|-1/-1|[a-z]+) counters among (?P<o>.+)", text)
    if m and rider is None:  # 601.2d: counters divided among the targets as the ability is put on the stack
        if m["k"] in values.UNMODELED_COUNTERS:
            raise _Fail
        return [{"do": "add_counters", "who": "target", "kind": m["k"], "n": {"divided": 0}}], \
            _divided(m["o"], "counters", _amount(m["n"]))
    m = re.fullmatch(rf"put (?P<n>{AMT}) (?P<k>\+1/\+1|-1/-1|[a-z]+) counters? on (?P<o>.+)", text)
    if m:
        kind, key, group = ref(m["o"])
        if kind == "players" or m["k"] in values.UNMODELED_COUNTERS:
            raise _Fail
        return [{"do": "add_counters", "who": _who(kind, key), "kind": m["k"], "n": _apply(_amount(m["n"]), rider)}], \
            _one(group)
    m = re.fullmatch(rf"remove (?P<n>{AMT}) (?P<k>\+1/\+1|-1/-1|[a-z]+) counters? from (?P<o>.+)", text)
    if m:
        kind, key, group = ref(m["o"])
        if kind == "players":
            raise _Fail
        return [{"do": "remove_counters", "who": _who(kind, key), "kind": m["k"], "n": _apply(_amount(m["n"]), rider)}], \
            _one(group)
    m = re.fullmatch(rf"(?P<o>.+?)(?: each)? gets? (?P<p>[+\-−]\d+)/(?P<t>[+\-−]\d+)(?: and gains? (?P<kw>{KEYWORDS}))? "
                     r"until end of turn", text)
    if m:
        kind, key, group = ref(m["o"])
        if kind == "players":
            raise _Fail
        who = _who(kind, key)
        out: Effects = [{"do": "pump", "who": who, "p": _signed(m["p"]), "t": _signed(m["t"])}]
        if m["kw"]:
            out.append({"do": "grant", "who": who, "keywords": [m["kw"]]})
        return out, _one(group)
    m = re.fullmatch(rf"(?P<o>.+?) gains? (?P<kw>{KEYWORDS}) until end of turn", text)
    if m:
        kind, key, group = ref(m["o"])
        if kind == "players":
            raise _Fail
        return [{"do": "grant", "who": _who(kind, key), "keywords": [m["kw"]]}], _one(group)
    raise _Fail


def _signed(p: str) -> int:
    return -int(p[1:]) if p[0] in "-−" else int(p.lstrip("+"))
