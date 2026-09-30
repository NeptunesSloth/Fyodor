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
# Player phrases. The pronouns are placeholders resolved by scripts.resolve_it against what the
# ability named earlier: "that player" → the target player (or the trigger event's player),
# "its controller" / "its owner" → the controller / owner of the object the previous instruction
# was about — as it was then, from last known information once it has left (608.2h, 108.4a).
PLAYER_GROUPS = {"you": "you", "each player": "each_player", "each opponent": "each_opponent",
                  "each of your opponents": "each_opponent", "that player": "that_player",
                  "its controller": "it.controller", "its owner": "it.owner",
                  "that creature's controller": "it.controller", "that permanent's controller": "it.controller",
                  "that card's owner": "it.owner", "that creature's owner": "it.owner"}
PLAYER_PHRASES = "|".join(sorted(PLAYER_GROUPS, key=len, reverse=True))


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


_THEM = ("them", "each of them", "they", "those creatures", "those permanents", "those cards", "those tokens")
# "cards exiled this way", "creatures sacrificed this way", "the exiled card": the objects a
# particular earlier instruction of this ability moved (400.7j: found where it put them)
_THIS_WAY = re.compile(r"^(?:the )?(?:cards?|creatures?|permanents?|tokens?|artifacts?|enchantments?|lands?) "
                       r"(?P<verb>exiled|sacrificed|destroyed|discarded|milled|returned) this way$")
_THE_VERBED = re.compile(r"^the (?P<verb>exiled|sacrificed|destroyed|discarded|milled|returned) "
                         r"(?P<what>card|creature|permanent|token|cards|creatures|permanents|tokens)$")


def ref(phrase: str) -> tuple[str, str, dict[str, Any] | None]:
    """An object or player phrase → ("target", selector key, target group) | ("each", selector
    key, None) | ("self", "", None) | ("players", "you" / "each_player" / "each_opponent", None) |
    a pronoun ("it" / "them", with the verb it names for "… exiled this way")."""
    p = phrase.strip()
    if p in ("~", "this creature", "this permanent"):
        return "self", "", None
    if p in ("it", "that creature", "that permanent", "that card", "that token"):
        return "it", "", None  # a pronoun: resolved against its antecedent (scripts.resolve_it)
    if p in _THEM:
        return "them", "", None  # the objects just named (scripts.resolve_it)
    m = _THIS_WAY.match(p) or _THE_VERBED.match(p)
    if m:
        plural = "what" not in m.groupdict() or m["what"].endswith("s")
        return ("them" if plural else "it"), m["verb"], None  # (resolved to that instruction's objects)
    if p in ("enchanted creature", "equipped creature", "enchanted permanent", "enchanted land", "enchanted artifact"):
        return "host", "", None  # what the source Aura / Equipment is attached to
    if p in PLAYER_GROUPS:
        return "players", PLAYER_GROUPS[p], None
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
    if kind in ("it", "them"):
        return f"{kind}:{key}" if key else kind  # "them:exiled": the objects the exile instruction moved
    return {"target": "target", "self": "self", "host": "host", "players": key, "each": key}[kind]


# -- dynamic values (agent F) -------------------------------------------------------------------
_STATS = {"power": "power", "toughness": "toughness", "mana value": "mana_value"}


def _stat(phrase: str, its: str = "it") -> Any:
    """"its power" / "that creature's toughness" / "its mana value": a value read from the object
    the previous instruction was about — as it is, or as it last existed (608.2h). A placeholder
    ("it") until scripts.resolve_it binds it; ``its`` is what "its" means when the sentence has
    its own subject ("~ deals damage equal to its power": ~'s). Also any quantity the value
    grammar reads ("the number of lands you control", "your devotion to red", "twice its power":
    app/rules/values.py), and "~'s power" (the source's, 608.2h)."""
    m = re.fullmatch(r"(?:(?P<its>its)|that creature's|that permanent's|that card's|(?P<self>~'s)) "
                     r"(?P<stat>power|toughness|mana value)", phrase)
    if m:
        return {_STATS[m["stat"]]: "self" if m["self"] else (its if m["its"] else "it")}
    m = re.fullmatch(r"twice (?P<v>.+)", phrase)
    if m:
        return {"times": [2, _stat(m["v"], its)]}
    v = values.parse_count(phrase)
    if v is None:
        raise _Fail
    return v


# The instruction joiners scripts._clause splits a sentence on (mirrored here, so a sentence with
# one "where X is …" for two instructions is read whole before it would be split)
_JOINER = (r", then | and (?=(?:you|target|each|~|it|that player|draw|lose|gain|put|return|exile|destroy|tap|untap|"
           r"create|sacrifice|discard|mill|scry|surveil)\b)")


def _has_x(v: Any) -> bool:
    """Does an effect (or value) use the placeholder X?"""
    if isinstance(v, list):
        return any(_has_x(x) for x in v)
    return isinstance(v, dict) and (v == {"x": 1} or any(_has_x(x) for x in v.values()))


def _bind_x(v: Any, value: Any) -> Any:
    """The effect with every X replaced by what "where X is …" defines."""
    if isinstance(v, list):
        return [_bind_x(x, value) for x in v]
    if isinstance(v, dict):
        return value if v == {"x": 1} else {k: _bind_x(x, value) for k, x in v.items()}
    return v


def _wants_target_player(v: Any) -> bool:
    """Does a value read a target player ("cards in target player's hand", "target player's life total")?"""
    if isinstance(v, list):
        return any(_wants_target_player(x) for x in v)
    if not isinstance(v, dict):
        return False
    return v.get("hand") == "target" or v.get("life") == "target" or any(_wants_target_player(x) for x in v.values())


def _value_target(n: Any, target: str | None) -> str | None:
    """The sentence's target once its amount is known: a value reading "target player" is that
    sentence's one target (115.1) — declared here so it's chosen on casting and checked on
    resolution — unless the sentence already targets something else (then it's not read)."""
    if not _wants_target_player(n):
        return target
    if target is None:
        return "player"
    if target in ("player", "opponent"):
        return target
    raise _Fail


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
    m = re.search(r",? where [xX] is (.+)$", text)  # (Oracle writes X; the lowercase form is the older tests')
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


_SUBJ = rf"(?:(?P<s>target player|target opponent|{PLAYER_PHRASES}) )?"


def _subject(m: re.Match[str]) -> tuple[str, str | None]:
    """(who, target key)"""
    if m["s"] is None and re.match(r"^\w+s\b", m.string):
        raise _Fail  # "discards a card" with no subject: someone else's (the lead's subject), not "you"
    s = m["s"] or "you"
    if s in ("target player", "target opponent"):
        return "target", _LEGACY_TARGETS[s]
    return PLAYER_GROUPS[s], None


_SEARCH = re.compile(
    rf"search your library for (?:(?P<upto>up to) )?(?P<n>{AMT}) (?P<sel>.+?), "
    r"(?:(?P<reveal>reveal (?:it|them|that card|those cards)), )?"
    r"(?:(?:put (?:it|them|that card|those cards) (?P<dest>into your hand|onto the battlefield tapped|onto the battlefield|"
    r"into your graveyard)|(?P<exile>exile (?:it|them|that card)(?P<fd> face down)?)), then shuffle"
    r"|then shuffle and put (?:that card|it) on top)")
_DESTS = {"into your hand": "hand", "onto the battlefield tapped": "battlefield_tapped", "onto the battlefield": "battlefield",
          "into your graveyard": "graveyard"}


def _search(text: str) -> tuple[Effects, str | None] | None:
    """701.23: "Search your library for [up to N] [card selector], [reveal it,] put it [where], then
    shuffle" (or "…, reveal it, then shuffle and put that card on top"; "exile it [face down]")."""
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
             "to": to, "reveal": bool(m["reveal"]), "upto": bool(m["upto"]),
             **({"face_down": True} if m["fd"] else {})}], None  # (only when the text says so: 701.23e)


# -- the top of a library (401, 701.20 reveal, 701.20e look, 701.24 shuffle) ----------------------
# Whose library: "your library" (default), a target player's (a target group), everyone's.
_LIB = r"(?P<lib>your|target player's|target opponent's|that player's|each player's|each opponent's) library"
_LIB_WHO = {"your": "you", "target player's": "target player", "target opponent's": "target opponent",
            "that player's": "that player", "each player's": "each player", "each opponent's": "each opponent"}
_SUBJECTS = r"(?P<subj>target player|target opponent|that player|each player|each opponent|each of your opponents)"
_N_CARDS = rf"(?:(?P<n>{AMT}) cards|card)"
_TOP = re.compile(rf"(?P<verb>look at|reveal) the top {_N_CARDS} of {_LIB}(?P<back>, then put them back in any order)?")
_SUBJ_TOP = re.compile(rf"{_SUBJECTS} (?P<verb>reveals|exiles) the top {_N_CARDS} of their library")
_EXILE_TOP = re.compile(rf"exile the top {_N_CARDS} of {_LIB}(?P<fd> face down)?")
_UNTIL = re.compile(rf"(?P<verb>reveal|exile) cards from the top of {_LIB} until you (?P=verb) (?:a|an) (?P<sel>.+)")
_REST = (r"(?:the rest|the other|the others|the other cards|all other cards revealed this way) "
         r"(?P<rest>into your graveyard|into your hand|on the bottom(?: of your library)? in (?:any|a random) order|"
         r"on the bottom of your library|on top of your library in any order)")
_PICK = re.compile(
    rf"(?:(?P<may>you may reveal) |(?P<mayput>you may put) |put )"
    rf"(?:(?P<q>up to {AMT}|any number of|{AMT}|all) (?:of them|of those cards|(?P<sel>.+?) (?:from among them|revealed this way))"
    r"|(?P<that>that card|it|the revealed card)|(?P<all>those cards|them|the revealed cards|all cards revealed this way))"
    r"(?: and put (?:it|them|the revealed cards|that card|those cards))?"
    r" (?P<to>into your hand|onto the battlefield tapped|onto the battlefield|into your graveyard)"
    rf"(?: and {_REST})?")
_REST_ALONE = re.compile(rf"(?:put {_REST}|exile (?P<exile>the rest|all other cards revealed this way))")
_OWNERS = r"(?:its owner's|their owner's|their owners'|your)"
_TO_LIBRARY = re.compile(rf"put (?P<o>.+?) (?P<place>on top|on the bottom) of {_OWNERS} library")
_SHUFFLE_INTO = re.compile(rf"shuffle (?P<o>.+?) into {_OWNERS} library")
_OWNER_SHUFFLES = re.compile(r"(?P<o>its|~'s|that card's|that creature's|that permanent's) owner shuffles it into their library")
_OWNER_CHOICE = re.compile(r"(?:the owner of (?P<o>.+?)|(?P<o2>.+?)'s owner) puts it on their choice of the top or bottom of their library")
_SHUFFLE = re.compile(rf"(?:then )?(?:(?P<may>you may )?shuffle(?: your library)?|shuffle your (?P<z>graveyard|hand and graveyard) into your library"
                      rf"|{_SUBJECTS} shuffles(?: their (?P<z2>graveyard|hand and graveyard) into their library)?)")


def _rest(where: str) -> dict[str, Any]:
    if where in ("into your graveyard", "into your hand"):
        to = where[len("into your "):]
    elif where.startswith("on top"):
        to = "top_any"
    else:
        to = "bottom_random" if "random" in where else "bottom_any"
    return {"do": "rest_looked", "to": to}


def _lib_owner(lib: str) -> tuple[str, dict[str, Any] | None]:
    """("you" / "each_player" / "target" …, the target group if a target player's library)."""
    kind, key, group = ref(_LIB_WHO[lib])
    return (_who(kind, key), group) if group is None else ("target", group)


def _card_sel(phrase: str) -> str:
    sel = selectors.parse(phrase)
    if sel is None or sel.player is not None or not sel.card:
        raise _Fail
    return sel.key()


def _looking(text: str) -> tuple[Effects, Any] | None:
    """The top of a library: "look at the top N cards of your library" (private, 701.20e) and
    "reveal the top N cards" (public, 701.20a), "… then put them back in any order" (401.4: the
    order is the chooser's secret), "reveal cards from the top of your library until you reveal a
    creature card", "exile the top N cards of your library [face down]", and what follows: "put
    one of them / that card / all land cards revealed this way into your hand / onto the
    battlefield / into your graveyard", "you may reveal a creature card from among them and put
    it into your hand", "and the rest on the bottom of your library in a random order / in any
    order / into your graveyard", "exile the rest". Also "put target creature on top / on the
    bottom of its owner's library", "shuffle ~ into its owner's library", "shuffle [your graveyard
    into your library]"."""
    text, rider = _with_rider(text) if re.match(r"^(?:look at|reveal|exile) the top", text) else (text, None)

    def count(m: re.Match[str]) -> Any:
        return _apply(_amount(m["n"]) if m["n"] else 1, rider)

    m = _TOP.fullmatch(text)
    if m:
        who, group = _lib_owner(m["lib"])
        out: Effects = [{"do": "look_top", "n": count(m), "player": who, "reveal": m["verb"] == "reveal"}]
        if m["back"]:
            if who not in ("you", "target", "that_player"):
                raise _Fail  # ("each player's library … put them back": who orders whose? not read)
            out.append({"do": "rest_looked", "to": "top_any"})
        return out, _one(group)
    m = _SUBJ_TOP.fullmatch(text)
    if m:
        kind, key, group = ref(m["subj"])
        do = "look_top" if m["verb"] == "reveals" else "exile_top"
        return [{"do": do, "n": count(m), "player": _who(kind, key), **({"reveal": True} if do == "look_top" else {})}], _one(group)
    m = _EXILE_TOP.fullmatch(text)
    if m:
        who, group = _lib_owner(m["lib"])
        return [{"do": "exile_top", "n": count(m), "player": who, "face_down": bool(m["fd"])}], _one(group)
    if rider is not None:
        raise _Fail
    m = _UNTIL.fullmatch(text)
    if m:
        who, group = _lib_owner(m["lib"])
        do = "look_top" if m["verb"] == "reveal" else "exile_top"
        return [{"do": do, "n": 0, "player": who, "until": _card_sel(m["sel"]), **({"reveal": True} if do == "look_top" else {})}], \
            _one(group)
    m = _PICK.fullmatch(text)
    if m:
        optional = bool(m["may"] or m["mayput"])
        e: dict[str, Any] = {"do": "pick_looked", "n": 1, "sel": None, "to": _DESTS[m["to"]], "optional": optional,
                             "reveal": bool(m["may"])}
        if m["q"]:
            q = m["q"]
            e["optional"] = optional or q.startswith(("up to", "any number"))
            e["n"] = 99 if q in ("any number of", "all") else _amount(q[6:] if q.startswith("up to ") else q)
            if m["sel"]:
                parsed = selectors.parse(m["sel"])
                if parsed is None or parsed.player is not None:
                    raise _Fail
                e["sel"] = parsed.key()
            elif q == "all":
                raise _Fail
        else:
            e["which"] = "that" if m["that"] else "all"
        out = [e]
        if m["rest"]:
            out.append(_rest(m["rest"]))
        return out, None
    m = _REST_ALONE.fullmatch(text)
    if m:
        return [{"do": "rest_looked", "to": "exile"} if m["exile"] else _rest(m["rest"])], None
    m = _SHUFFLE.fullmatch(text)
    if m:
        who, group = ("you", None)
        if m["subj"]:
            kind, key, group = ref(m["subj"])
            who = _who(kind, key)
        zones = {"graveyard": ["graveyard"], "hand and graveyard": ["hand", "graveyard"]}.get(m["z"] or m["z2"] or "", [])
        return [{"do": "shuffle_library", "who": who, "zones": zones, **({"optional": True} if m["may"] else {})}], _one(group)
    m = _TO_LIBRARY.fullmatch(text) or _SHUFFLE_INTO.fullmatch(text)
    if m:
        kind, key, group = ref(m["o"])
        if kind not in ("target", "self", "it", "them"):
            raise _Fail  # ("put two cards from your hand on top": which two? not read)
        place = "shuffle" if "place" not in m.groupdict() else ("top" if m["place"] == "on top" else "bottom")
        return [{"do": "to_library", "who": _who(kind, key), "place": place}], _one(group)
    m = _OWNER_SHUFFLES.fullmatch(text)
    if m:
        return [{"do": "to_library", "who": "self" if m["o"] == "~'s" else "it", "place": "shuffle"}], None
    m = _OWNER_CHOICE.fullmatch(text)
    if m:
        kind, key, group = ref(m["o"] or m["o2"])
        if kind not in ("target", "self", "it"):
            raise _Fail
        return [{"do": "to_library", "who": _who(kind, key), "place": "choice"}], _one(group)
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
    if rider is not None and rider[0] == "x":
        # "Each opponent loses X life and you gain X life, where X is …": one X for both halves
        # (107.3c: X is defined by the text of the ability for the whole ability), so the halves
        # are read here, each with the rider, rather than split upstream with X unbound in one
        halves = re.split(_JOINER, text, maxsplit=1)
        if len(halves) == 2:
            left, right = _parse(halves[0]), _parse(halves[1])
            if left[1] is not None and right[1] is not None:
                raise _Fail  # (two targets: not read here)
            if not all(_has_x(e) for e in (*left[0], *right[0])):
                raise _Fail  # ("… and draw a card, where X is …": which half X belongs to isn't read)
            return [_bind_x(e, rider[1]) for e in (*left[0], *right[0])], left[1] if left[1] is not None else right[1]
    # -- players ------------------------------------------------------------------------------
    m = re.fullmatch(_SUBJ + rf"draws? (?:(?P<n>{AMT}) cards?|cards equal to (?P<stat>.+))", text)
    if m:
        who, target = _subject(m)
        if m["stat"]:  # "draw cards equal to its power" (a trigger's object, or an earlier instruction's)
            if rider is not None:
                raise _Fail
            n = _stat(m["stat"])
            return [{"do": "draw", "who": who, "n": n}], _value_target(n, target)
        return [{"do": "draw", "who": who, "n": _apply(_amount(m["n"]), rider)}], target
    m = re.fullmatch(_SUBJ + rf"(?P<v>gains?|loses?) (?:(?P<n>{AMT}) life|life equal to (?P<stat>.+))", text)
    if m:
        who, target = _subject(m)
        verb = "gain_life" if m["v"].startswith("gain") else "lose_life"
        if m["stat"]:  # "… gains life equal to its toughness"
            if rider is not None:
                raise _Fail
            n = _stat(m["stat"])
            return [{"do": verb, "who": who, "n": n}], _value_target(n, target)
        return [{"do": verb, "who": who, "n": _apply(_amount(m["n"]), rider)}], target
    m = re.fullmatch(_SUBJ + rf"(?P<v>discards?|mills?) (?:(?P<n>{AMT}) cards?|cards equal to (?P<stat>.+))", text)
    if m:
        who, target = _subject(m)
        verb = "discard" if m["v"].startswith("discard") else "mill"
        if m["stat"]:
            if rider is not None:
                raise _Fail
            n = _stat(m["stat"])
            return [{"do": verb, "who": who, "n": n}], _value_target(n, target)
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
    m = re.fullmatch(rf"(?P<src>~|it) deals (?:(?P<n>{AMT}) damage|damage equal to (?P<stat>.+?)) to (?P<o>.+)", text)
    if m is None:  # "~ deals damage to target creature equal to the number of lands you control" (the same, worded after)
        m = re.fullmatch(r"(?P<src>~|it) deals (?P<n>)damage to (?P<o>.+?) equal to (?P<stat>.+)", text)
    if m:
        if m["stat"] and rider is not None:
            raise _Fail
        # "~ deals damage equal to its power": its own (the subject's); "it deals … its power": it's
        n = _stat(m["stat"], "self" if m["src"] == "~" else "it") if m["stat"] else _apply(_amount(m["n"]), rider)
        if _wants_target_player(n):
            raise _Fail  # (a second target the damage sentence would have to declare: not read)
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
        if kind in ("players", "self"):
            raise _Fail
        sel = selectors.from_key(key) if key.startswith(selectors.PREFIX) else None
        # a pronoun names cards an earlier instruction put in a graveyard or exile (400.7j:
        # "Exile target creature. Return it to the battlefield …" finds it there)
        from_zone = (sel is not None and sel.card) or kind in ("it", "them")
        who = _who(kind, key)
        target = _one(group)
        if m["d"].startswith("the battlefield"):
            if not from_zone:
                raise _Fail  # (blink wordings are templated elsewhere)
            return [{"do": "return_card", "who": who, "to": "battlefield", "tapped": bool(m["t"]),
                     "under": "you" if m["u"] == "your" else "owner"}], target
        if from_zone and kind not in ("it", "them"):
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


# -- player choices (agent I) ---------------------------------------------------------------------
# Sentences whose choice belongs to a named player, read by the templates registered at the end of
# app/rules/scripts.py (they run before the generic grammar): edicts — "[each opponent / target
# player / that player] sacrifices N [selector] of their choice" (701.21a: the sacrificing player
# chooses; several players in APNAP order, 101.4, each knowing the earlier choices, 101.4b, then
# all at once); "[target opponent] chooses N [selector] they control"; a revealed hand — "target
# player reveals their hand" (701.20a), "you [may] choose [up to] N [card selector] from it", "that
# player discards that card"; and a named choice — "choose a color / creature type / basic land
# type / opponent / player" (105.1, 205.3m, 205.3i). "As ~ enters, choose …" (614.1c, 614.12a) is
# read by ``enters_choice`` for the engine's entering code; it is not a resolution effect.
_CHOOSERS = ("target player", "target opponent", "each opponent", "each of your opponents", "each player", "each other player",
             "that player", "its controller", "that creature's controller", "that permanent's controller", "defending player")
CHOOSER = "|".join(re.escape(c) for c in sorted(_CHOOSERS, key=len, reverse=True))
# (patterns are format()-ed by scripts.effect: no literal braces)
EDICT = rf"(?P<s>{CHOOSER}) sacrifices (?P<n>{AMT}) (?P<sel>.+?) of their choice"
EDICT_OTHERS = rf"each other player sacrifices (?P<n>{AMT}) (?P<sel>.+?)(?: of their choice)?"
PLAYER_CHOOSES = rf"(?P<s>{CHOOSER}) chooses (?P<n>{AMT}) (?P<sel>.+?) they control"
REVEAL_HAND = rf"(?P<s>{CHOOSER}) reveals their hand"
CHOOSE_FROM_HAND = (rf"you (?P<may>may )?choose (?:(?P<upto>up to )?(?P<n>{AMT})|(?P<any>any number of)) (?P<sel>.+?) "
                    r"from (?:it|among them|that hand)")
DISCARD_NAMED = r"(?:that player|they|its owner) discards? (?P<o>that card|those cards|it|them)"
CHOICE_KINDS = ("color", "creature type", "basic land type", "opponent", "player")
CHOOSE_VALUE = r"choose (?:a|an) (?P<what>color|creature type|basic land type|opponent|player)"
ENTERS_CHOICE = re.compile(r"^As ~ enters, choose (?:a|an) (?P<what>color|creature type|basic land type|opponent|player)\.$")


def _chooser(s: str) -> tuple[str, Any]:
    """A choosing player's phrase → ("who", the target group it adds)."""
    if s in ("target player", "target opponent"):
        return "target", {"what": _LEGACY_TARGETS[s], "min": 1, "max": 1}
    if s == "each other player":
        return "each_opponent", None  # every other player is an opponent in a free-for-all (102.2, 806.2)
    if s == "defending player":
        raise _Fail  # which defending player (508.5)? the trigger event doesn't carry it: manual
    return PLAYER_GROUPS[s], None


def _permanent_sel(phrase: str) -> str:
    """"creature", "creature or planeswalker", "nontoken artifact", "permanent" — a permanent
    selector (no player, not a card in another zone, no controller: the chooser's own)."""
    sel = selectors.parse(phrase)
    if sel is None or sel.player is not None or sel.card or sel.zones != ("battlefield",) or sel.controller is not None:
        raise _Fail
    return sel.key()


def edict(m: re.Match[str]) -> tuple[Effects, Any]:
    who, group = _chooser(m["s"] if "s" in m.groupdict() else "each other player")
    key = _permanent_sel(m["sel"])
    return [{"do": "edict", "who": who, "sel": key, "n": _amount(m["n"]), "label": m["sel"]}], _one(group)


def player_chooses(m: re.Match[str]) -> tuple[Effects, Any]:
    who, group = _chooser(m["s"])
    return [{"do": "player_chooses", "who": who, "sel": _permanent_sel(m["sel"]), "n": _amount(m["n"]), "label": m["sel"]}], \
        _one(group)


def reveal_hand(m: re.Match[str]) -> tuple[Effects, Any]:
    who, group = _chooser(m["s"])
    if who in ("each_player", "each_opponent"):
        raise _Fail  # ("each opponent reveals their hand. You choose a card from it": from whose? not read)
    return [{"do": "reveal_hand", "who": who}], _one(group)


def choose_from_hand(m: re.Match[str]) -> tuple[Effects, Any]:
    sel = selectors.parse(m["sel"])
    if sel is None or sel.player is not None or not sel.card or sel.zones:
        raise _Fail  # (a card in the hand: "a nonland card", "an instant or sorcery card" — nothing else)
    n = 99 if m["any"] else _amount(m["n"])
    if not isinstance(n, int):
        raise _Fail
    return [{"do": "choose_from_hand", "who": "you", "sel": sel.key(), "n": n, "label": m["sel"],
             "optional": bool(m["may"] or m["upto"] or m["any"])}], None


def discard_named(m: re.Match[str]) -> tuple[Effects, Any]:
    return [{"do": "discard_named", "who": "it" if m["o"] in ("that card", "it") else "them"}], None


def choose_value(m: re.Match[str]) -> tuple[Effects, Any]:
    return [{"do": "choose_value", "who": "you", "what": m["what"]}], None


def enters_choice(text: str) -> dict[str, Any] | None:
    """"As ~ enters, choose a color / a creature type / an opponent …" (614.1c: a replacement effect
    of the permanent; 614.12a: the choice is made before it enters; 603.6d: not a trigger). The
    definition for the engine's entering code (app/rules/engine.py, attachments.enter): the
    ``choose_value`` effect with ``remember`` writes the answer on the object as its public
    ``choices`` entry. Not registered as a template until the engine asks for it as the permanent
    enters — the choice must not be modeled as an enters trigger."""
    m = ENTERS_CHOICE.match(text)
    if m is None:
        return None
    return {"kind": "replacement", "replacement": "enters_choice",
            "effects": [{"do": "choose_value", "who": "you", "what": m["what"], "remember": True}]}
