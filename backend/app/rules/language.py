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
    # -- target forms (agent T) --  a player, or any planeswalker (whoever controls it)
    "target player or planeswalker": "player_or_planeswalker", "target opponent or planeswalker": "opponent_or_planeswalker",
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
# -- target forms (agent T) --  "up to one other target creature", "each of up to two other targets",
# "any number of other target nonland permanents you control": "other" inside a counted group
_GROUP = re.compile(rf"^(?:each of )?(?:up to (?P<upto>{_QTY})|(?P<range>one or two|one, two, or three)|"
                    rf"(?P<any>any number of)|(?P<n>{_QTY})) (?P<other>(?:an)?other )?(?P<rest>targets|target .+)$")


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
    if p in ("another target", "any other target"):  # 115.4 (Arc Trail): any target other than the earlier one
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
    if m["other"]:  # "up to two other target creatures": other than the source, or than an earlier target
        if m["rest"] == "targets":
            what, constraints = "", {"another": "any"}  # ("each of up to two other targets": than the earlier one)
        else:
            constraints = {**constraints, "another": what}
            what = _group_constraints(_target_key("another " + m["rest"]))[0]
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
_AND_TARGET = (r" and (?=(?:each of )?(?:another |up to \w+ |any number of |one or two |two |three )?(?:(?:an)?other )?targets?\b"
               r"|any (?:other )?target)")


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
    the value of X (None if there's none). A rider may read the object the sentence is about
    ("where X is its power", "for each +1/+1 counter on it"): a placeholder "it", bound by
    scripts.resolve_it for an amount, or by the pump grammar to its own subject."""
    m = re.search(r",? where [xX] is (.+)$", text)  # (Oracle writes X; the lowercase form is the older tests')
    if m:
        return text[: m.start()], ("x", _rider_value(m[1]))
    m = re.search(r" for each (.+)$", text)
    if m:
        return text[: m.start()], ("each", _rider_value(m[1]))
    return text, None


def _rider_value(phrase: str) -> Any:
    """A rider's quantity: "its power" / "that creature's toughness" / "~'s power" (app: _stat),
    else any counted phrase (values.parse_count; "counters on it" with "it" as a placeholder)."""
    if re.fullmatch(r"(?:its|that creature's|that permanent's|that card's|~'s) (?:power|toughness|mana value)", phrase):
        return _stat(phrase)
    v = values.parse_count(phrase, it="it")
    if v is None:
        raise _Fail
    return v


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


# -- tutors (wave 3T) -- one grammar for a library search: what is searched for (a selector, a name,
# a mana value that may be X), whether it is revealed, where it goes (one place, or "one … and the
# other …"), and whether the library is shuffled (701.23, 701.24).
_PRON = r"(?:it|them|that card|those cards|the card|the cards)"
_PLACE = r"(?:into your hand|onto the battlefield tapped|onto the battlefield|into your graveyard)"
_SEARCH = re.compile(
    rf"search your library for (?:(?P<upto>up to) )?(?P<n>{AMT}) (?P<sel>.+?)(?:,? and |, )"
    rf"(?:(?P<reveal>reveal {_PRON})(?:,? and |, ))?"
    rf"(?:put (?:(?P<one>one) (?P<d1>{_PLACE}) and the other (?P<d2>{_PLACE})|{_PRON} (?P<dest>{_PLACE}))(?P<shuf>, then shuffle)?"
    rf"|(?P<exile>exile {_PRON}(?P<fd> face down)?)(?P<shuf2>, then shuffle)?"
    rf"|then shuffle and put {_PRON} on top)")
_DESTS = {"into your hand": "hand", "onto the battlefield tapped": "battlefield_tapped", "onto the battlefield": "battlefield",
          "into your graveyard": "graveyard"}
_MV_X = re.compile(r"(?P<rest>.+?),? with mana value [xX](?P<less> or less)?")
_NAMED = re.compile(r"(?P<rest>card|cards) named (?P<name>.+)")


def _search(text: str) -> tuple[Effects, str | None] | None:
    """701.23: "Search your library for [up to N] [card selector], [reveal it,] put it [where], then
    shuffle" (or "…, reveal it, then shuffle and put that card on top"; "exile it [face down]";
    "put one onto the battlefield and the other into your hand"). A card "named …", or with "mana
    value X or less" (the X the spell or ability has), is searched for too. Without "then shuffle"
    the library is not shuffled (701.24 shuffles only when told to)."""
    m = _SEARCH.fullmatch(text)
    if not m:
        return None
    extra: dict[str, Any] = {}
    sel_text = m["sel"]
    named = _NAMED.fullmatch(sel_text)
    if named:
        extra["name"] = named["name"]
        sel_text = named["rest"]
    mv = _MV_X.fullmatch(sel_text)
    if mv:
        extra["mv"] = ["<=" if mv["less"] else "==", _amount("x")]
        sel_text = mv["rest"]
    sel = selectors.parse(sel_text)
    if sel is None or sel.player is not None or not sel.card:
        raise _Fail
    sel = selectors.replace(sel, zones=("library",), zone_owner="you", card=True)
    n = _amount(m["n"])
    if m["one"]:
        if n != 2:
            raise _Fail
        to, extra["to2"] = _DESTS[m["d1"]], _DESTS[m["d2"]]
    elif m["exile"]:
        to = "exile"
    elif m["dest"]:
        to = _DESTS[m["dest"]]
    else:
        to = "top"
    if to != "top" and not (m["shuf"] or m["shuf2"]):
        extra["shuffle"] = False  # (only when the text says so: 701.23e)
    return [{"do": "search", "who": "you", "sel": sel.key(), "label": m["sel"], "max": n,
             "to": to, "reveal": bool(m["reveal"]), "upto": bool(m["upto"]),
             **({"face_down": True} if m["fd"] else {}), **extra}], None


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
    if '"' in text:  # -- quoted grants (wave 2D) -- the quoted abilities are read on their own
        return _quoted(text)
    lead = _EOT_LEAD.match(text)  # -- quoted grants (wave 2D) -- "Until end of turn, target creature gets +1/+0."
    if lead:
        return _end_of_turn_first(lead["rest"])
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
    found = _bite(text)  # -- temporary grants & riders (agent G) --  "target creature you control deals damage equal to its power to …"
    if found is not None:
        if rider is not None:
            raise _Fail
        return found
    if rider is not None and not text.startswith(("put ", "remove ")) and not re.search(r"\bgets? [+\-−]", text):
        raise _Fail
    # -- objects --------------------------------------------------------------------------------
    found = _target_forms(text)  # -- target forms (agent T) --
    if found is not None:
        return found
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
    if m and not _PUMP.fullmatch(text):  # (agent G: "… gets +2/+2 until end of turn and can't be blocked …" is a pump's rider)
        kind, key, group = ref(m["o"])
        if kind == "players":
            raise _Fail
        return [{"do": "restrict", "who": _who(kind, key), "rules": RESTRICTIONS[m["r"]]}], _one(group)
    if text in ("return ~ to its owner's hand", "return it to its owner's hand"):
        return [{"do": "bounce", "who": "self" if text.startswith("return ~") else "it"}], None
    m = re.fullmatch(r"return (?P<o>.+?) to (?P<d>its owner's hand|their owners' hands|their owner's hand|your hand|"
                     r"the battlefield(?P<t> tapped)?(?: under (?P<u>your|its owner's|their owners') control)?"
                     r"(?: with (?:an?|one) (?P<ck>\+1/\+1|-1/-1|[a-z]+) counter on it)?)", text)
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
            if m["ck"] and m["ck"] in values.UNMODELED_COUNTERS:
                raise _Fail
            # (-- quoted grants, wave 2D -- "… with a +1/+1 counter on it": it enters with it, 122.6)
            return [{"do": "return_card", "who": who, "to": "battlefield", "tapped": bool(m["t"]),
                     "under": "you" if m["u"] == "your" else "owner", **({"counter": m["ck"]} if m["ck"] else {})}], target
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
        if m["k"] in values.UNMODELED_COUNTERS:
            raise _Fail
        whos, groups = _objects(m["o"])  # -- target forms (agent T) --  "on up to one target land and up to one target creature"
        if len(whos) > 1:
            if len(groups) != len(whos):
                raise _Fail  # (each part of "… and …" is a target of its own: 115.3)
            return [{"do": "add_counters", "who": w, "kind": m["k"], "n": _apply(_amount(m["n"]), rider)} for w in whos], \
                _out(groups)
        kind, key, group = ref(m["o"])
        if kind == "players":
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
    # -- temporary grants & riders (agent G) --  "+X/+0", "+1/+1 … for each …", "-X/-X … where X is …",
    # "gets +2/+2 and gains flying and first strike", "… and can't be blocked this turn", "loses flying"
    m = _PUMP.fullmatch(text)
    if m:
        return _pump(m, rider)
    m = _LOSE_GAIN.fullmatch(text)  # -- quoted grants (wave 2D) -- "This creature loses defender and gains ⟦0⟧"
    if m:
        kind, key, group = ref(m["o"])
        if kind == "players":
            raise _Fail
        e = _grant_effect(_who(kind, key), m["kw"])
        if "quotes" not in e:
            raise _Fail  # (keywords only: not read here)
        e = {**e, "remove": _keyword_list(m["rm"])}
        return [e if m["eot"] else {**e, "duration": "permanent"}], _one(group)
    m = _GRANT.fullmatch(text)
    if m:
        kind, key, group = ref(m["o"])
        if kind == "players":
            raise _Fail
        e = _grant_effect(_who(kind, key), m["kw"])
        if m["v"].startswith("lose"):
            if "quotes" in e:
                raise _Fail  # ("loses ⟦…⟧": nothing to take away by quoting it)
            e = {**e, "keywords": [], "remove": e["keywords"]}
        return [e], _one(group)
    m = _GRANT_GAME.fullmatch(text)  # -- quoted grants (wave 2D) -- no duration stated: the game (611.2a)
    if m:
        kind, key, group = ref(m["o"])
        if kind == "players":
            raise _Fail
        e = _grant_effect(_who(kind, key), m["kw"])
        if "quotes" not in e:
            raise _Fail  # (a bare "gains flying" with no duration: not a clause this grammar reads)
        return [{**e, "duration": "permanent"}], _one(group)
    raise _Fail


def _signed(p: str) -> int:
    return -int(p[1:]) if p[0] in "-−" else int(p.lstrip("+"))


# -- target forms (agent T) ---------------------------------------------------------------------------
# Sentences whose whole point is their targets (CR 115, 601.2c): "Choose up to one target creature."
# (a later sentence acts on it: "That creature can't block this turn"), "[~ / it / target creature
# you control] fights [another] target creature" (701.14: two words "target", so two groups, and
# "another" means an object distinct from the first, 115.3), and "counter [target spell /
# activated or triggered ability]" (115.1c-d; a mana ability never uses the stack, 605.3a). A
# sentence is only read when the engine has the primitive that carries it out: the ones whose
# primitive another module hasn't added yet are refused (app/rules/coverage.py REFUSED).
_CHOOSE = re.compile(r"choose (?P<o>(?:each of )?(?:up to \w+ |any number of |one or two |\w+ )?(?:(?:an)?other )?targets?\b.*)")
_FIGHTS = re.compile(r"(?P<a>.+?) fights (?P<b>.+)")
_COUNTER = re.compile(r"counter (?P<o>.+)")


def has_primitive(name: str) -> bool:
    """Does the effects module carry out this primitive? (Never claim a wording the engine can't run.)"""
    from app.rules import effects  # (effects imports this module's users; a lazy import)

    return name in effects.PRIMITIVES


def _target_forms(text: str) -> tuple[Effects, Any] | None:
    m = _CHOOSE.fullmatch(text)
    if m:
        if not has_primitive("choose_targets"):
            raise _Fail  # (refused until the primitive exists: coverage.REFUSED "choose_targets")
        whos, groups = _objects(m["o"])
        if len(whos) != len(groups):
            raise _Fail  # ("choose a creature": a choice, not a target — the player-choices grammar)
        return [{"do": "choose_targets", "who": w} for w in whos], _out(groups)
    m = _FIGHTS.fullmatch(text)
    if m:
        if not has_primitive("fight"):
            raise _Fail  # (refused until the fight primitive exists: coverage.REFUSED "fight")
        a_kind, a_key, a_group = ref(m["a"])
        b_kind, b_key, b_group = ref(m["b"])
        if a_kind not in ("self", "it", "host", "target") or b_kind != "target":
            raise _Fail  # (a creature fights "each creature …": one at a time, in what order? not read)
        groups = [g for g in (a_group, b_group) if g is not None]
        for g in groups:
            if not g["what"].startswith(selectors.PREFIX) or selectors.from_key(g["what"]).player is not None:
                raise _Fail  # (only creatures fight, 701.14a: "any target" can't be one)
        who = "target" if a_group is not None else _who(a_kind, a_key)
        partner = "target" if a_group is None else "target:1"
        return [{"do": "fight", "who": who, "with": partner}], _out(groups)
    m = _COUNTER.fullmatch(text)
    if m:
        kind, key, group = ref(m["o"])
        if kind != "target" or not key.startswith(selectors.PREFIX) or selectors.from_key(key).zones != ("stack",):
            raise _Fail  # (only an object on the stack can be countered, 701.6a)
        return [{"do": "counter", "who": "target"}], _one(group)
    return None


# -- temporary grants & riders (agent G) ---------------------------------------------------------------
# Pumps and keyword grants "until end of turn" with what rides on them, researched against CR
# 2026-09-25: the amount may be X (107.3: chosen on activation, or defined by "where X is …",
# 107.3c) or "for each …" — a value read ONCE, as the effect begins (611.2d, 608.2h: "Creatures
# you control get +1/+1 until end of turn for each creature you control" is locked when it
# resolves, unlike a static's "for each", 611.3a); several keywords ("gains flying and first
# strike"); a rules rider in the same sentence ("… until end of turn and can't be blocked this
# turn", two effects: 611.2c's parts); "loses flying until end of turn" (layer 6 removal,
# 613.1f); a bite ("target creature you control deals damage equal to its power to target creature
# you don't control": the first creature is the damage source, so ITS lifelink and deathtouch
# count, 120.3f, 702.2b; "src" names it). Refused, never guessed: a granted quoted ability with a
# duration (the resolved-effect layer model carries keywords only), "gains flashback until end of
# turn" (a casting permission from the graveyard), "where X is" a quantity the value grammar
# doesn't read, "its power" for a pronoun subject the pump can't bind itself.
_GRANT_ITEM = rf"(?:{KEYWORDS}|⟦\d+⟧)"  # (a keyword, or -- wave 2D -- a quoted ability set aside as ⟦n⟧)
_KW_LIST = rf"{_GRANT_ITEM}(?:(?:, and |, | and ){_GRANT_ITEM})*"
_PUMP = re.compile(rf"(?P<o>.+?)(?: each)? gets? (?P<p>[+\-−](?:\d+|[xX]))/(?P<t>[+\-−](?:\d+|[xX]))"
                   rf"(?: and gains? (?P<kw>{_KW_LIST}))? until end of turn"
                   r"(?: and can't (?P<r>attack or block|block|attack|be blocked) this turn)?")
_GRANT = re.compile(rf"(?P<o>.+?)(?: each)? (?P<v>gains?|has|have|loses?) (?P<kw>{_KW_LIST}) until end of turn")
_GRANT_GAME = re.compile(rf"(?P<o>.+?)(?: each)? (?:gains?|has|have) (?P<kw>{_KW_LIST})")  # (quoted abilities only: see _parse)
_KW_ONLY = rf"(?:{KEYWORDS})(?:(?:, and |, | and )(?:{KEYWORDS}))*"
_LOSE_GAIN = re.compile(rf"(?P<o>.+?) loses? (?P<rm>{_KW_ONLY}) and gains? (?P<kw>{_KW_LIST})(?P<eot> until end of turn)?")
_BITE = re.compile(r"(?P<s>.+?) deals damage equal to (?P<stat>its power|its toughness|that creature's power) to (?P<o>.+)")
_ITS = {"target": "target", "self": "self", "host": "host"}  # what "its" names for a pump's subject


def _keyword_list(text: str) -> list[str]:
    return re.split(r", and | and |, ", text)


# -- quoted grants (wave 2D: app/rules/granted.py) ----------------------------------------------------
# "Until end of turn, target creature gets +2/+0 and gains "When this creature dies, return it to the
# battlefield tapped under its owner's control."" (Supernatural Stamina), "Until end of turn, creatures
# you control gain "{T}: This creature deals 1 damage to any target."" (Lightning Volley), "Return
# target creature card … to the battlefield. It gains "If this creature would die, exile it
# instead."" (Can't Stay Away: no duration, so the game, 611.2a). A sentence with quoted abilities is
# read with each quote set aside as ⟦n⟧ — so nothing inside it is taken for the sentence's own
# words (its "until end of turn", its "for each …") — and each quote checked on its own
# (granted.quote); the grants then carry their texts. A leading "Until end of turn," reads as the
# trailing wording the grammar above knows (611.2a: the same duration).
_EOT_LEAD = re.compile(r"^until end of turn, (?P<rest>.+)$")
_RESTRICT_TAIL = re.compile(r"^.+? can't (?:attack or block|block|attack|be blocked)$")


def _grant_effect(who: str, items: str) -> dict[str, Any]:
    """"flying, first strike, and ⟦0⟧" → one grant: the keywords, and the quoted abilities (their numbers)."""
    from app.rules import granted

    words, quotes = granted.items(items)
    e: dict[str, Any] = {"do": "grant", "who": who, "keywords": words}
    if quotes:
        e["quotes"] = quotes
    return e


def _end_of_turn_first(rest: str) -> tuple[Effects, Any]:
    """"Until end of turn, <clause>": the clause with the duration after it, if that is a continuous
    effect (only a pump, a grant or a restriction has one: delayed.wrap_duration's rule)."""
    effects, target = _parse(rest + (" this turn" if _RESTRICT_TAIL.fullmatch(rest) else " until end of turn"))
    if not effects or any(e["do"] not in ("pump", "grant", "restrict") for e in effects):
        raise _Fail
    return effects, target


def _quoted(text: str) -> tuple[Effects, Any]:
    """A sentence with quoted abilities (see above): only a grant may carry them, and every quote
    must be carried out by the engine (granted.quote) and used."""
    from app.rules import granted

    parts = granted.protect(text)
    if parts is None or not parts[1]:
        raise _Fail
    safe, quotes = parts
    checked = [granted.quote(q) for q in quotes]  # (an ability the engine carries out as granted …)
    ruled = [granted.rules_of(q) if c is None else None for q, c in zip(quotes, checked, strict=True)]  # (… or a rule)
    if any(c is None and r is None for c, r in zip(checked, ruled, strict=True)):
        raise _Fail
    effects, target = _parse(safe)
    used: list[int] = []
    out: Effects = []
    for e in effects:
        e = dict(e)
        numbers = e.pop("quotes", None)
        if not numbers:
            out.append(e)
            continue
        used += numbers
        rules = [rule for i in numbers for rule in (ruled[i] or ())]
        abilities = [c for i in numbers if (c := checked[i]) is not None]
        if abilities:
            e["abilities"] = abilities
        if abilities or e["keywords"] or e.get("remove"):
            out.append(e)
        if rules:  # "gains "This creature can't be blocked."": a restriction on the same objects (granted.rules_of)
            out.append({"do": "restrict", "who": e["who"], "rules": list(dict.fromkeys(rules)), "locked": True,
                        **({"duration": e["duration"]} if "duration" in e else {})})
    if sorted(used) != list(range(len(quotes))) or not _permanents(out, target):
        raise _Fail
    return out, target


def _permanents(effects: Effects, target: Any) -> bool:
    """Does every grant of quoted abilities name permanents? A card in a graveyard or exile, or a
    spell, doesn't gain an ability an effect grants (611.2e: only a permanent on the battlefield
    does): those stay manual. A pronoun is read when it resolves (effects.grant skips what isn't there)."""
    from app.rules.scripts import SELECTORS  # (scripts imports this module)

    keys = [e["who"] for e in effects if e["do"] in ("grant", "restrict") and isinstance(e.get("who"), str)]
    groups = [g["what"] if isinstance(g, dict) else g for g in (target if isinstance(target, list) else [target]) if g]
    not_permanents = {"any", "player", "opponent", "spell", "creature_spell", "noncreature_spell", "instant_or_sorcery_spell"}
    legacy = {v for v in SELECTORS.values() if v not in not_permanents}  # ("target creature", "target land", …)
    for key in (*keys, *groups):
        if not isinstance(key, str):
            return False
        if key.startswith(selectors.PREFIX):
            sel = selectors.from_key(key)
            if sel.zones != ("battlefield",) or sel.player is not None:
                return False
        elif key in not_permanents or key.startswith(("graveyard:", "stack", "player")) or (
                key not in legacy and not key.startswith(("target", "it", "them", "self", "host", "ref:", "event", "object:"))
                and key not in ("creatures_you_control", "each_creature")):
            return False
    return True


def _bind_its(v: Any, its: str | None) -> Any:
    """A rider's placeholder "it" ("where X is its power", "for each counter on it") as the pump's
    own subject; refused when the subject is a pronoun the grammar can't bind here."""
    if isinstance(v, list):
        return [_bind_its(x, its) for x in v]
    if not isinstance(v, dict):
        return v
    out = {}
    for k, x in v.items():
        if k in ("power", "toughness", "mana_value", "on") and x == "it":
            if its is None:
                raise _Fail
            x = its
        else:
            x = _bind_its(x, its)
        out[k] = x
    return out


def _mod(word: str, rider: Any, its: str | None) -> Any:
    """One half of "+N/+N": an int, or a value expression ("+X", "-X", "+2 for each …": ``{"neg":
    …}`` for a negative one, evaluated by values.evaluate_signed as the pump begins)."""
    neg = word[0] in "-−"
    body = word[1:]
    base: Any = {"x": 1} if body.lower() == "x" else int(body)
    if rider is not None:
        kind, v = rider
        v = _bind_its(v, its)
        if kind == "x":
            if base == {"x": 1}:
                base = v
        elif base == {"x": 1}:
            raise _Fail  # ("+X/+X for each …": no such wording is read)
        elif base:
            base = v if base == 1 else {"times": [base, v]}
    if isinstance(base, int):
        return -base if neg else base
    return {"neg": base} if neg else base


def _pump(m: re.Match[str], rider: Any) -> tuple[Effects, Any]:
    kind, key, group = ref(m["o"])
    if kind == "players":
        raise _Fail
    who = _who(kind, key)
    its = _ITS.get(kind)
    p, t = _mod(m["p"], rider, its), _mod(m["t"], rider, its)
    if rider is not None and rider[0] == "x" and "x" not in (m["p"] + m["t"]).lower():
        raise _Fail  # "where X is …" with no X in the sentence
    out: Effects = [{"do": "pump", "who": who, "p": p, "t": t}]
    if m["kw"]:
        out.append(_grant_effect(who, m["kw"]))
    if m["r"]:
        out.append({"do": "restrict", "who": who, "rules": RESTRICTIONS[m["r"]]})
    return out, _one(group)


def _shift(who: str, by: int) -> str:
    """A target reference of a later part of the sentence, after ``by`` earlier groups."""
    if who == "target":
        return f"target:{by}"
    if who.startswith("target:"):
        return f"target:{int(who[7:]) + by}"
    return who


def _bite(text: str) -> tuple[Effects, Any] | None:
    """"[Target creature you control / enchanted creature] deals damage equal to its power to
    [target creature you don't control / each creature …]": damage whose source is the named
    creature (120.3, 608.2h: as it is, or as it last existed). "~" and "it" as the subject are the
    older damage grammar's."""
    m = _BITE.fullmatch(text)
    if m is None or m["s"] in ("~", "it"):
        return None
    kind, key, group = ref(m["s"])
    if kind not in ("target", "host"):
        raise _Fail  # (a pronoun subject: which creature deals it isn't read here)
    stat = "toughness" if "toughness" in m["stat"] else "power"
    src = "target" if group is not None else "host"
    groups = [group] if group is not None else []
    whos, parts = _objects(m["o"])
    effects: Effects = [{"do": "damage", "who": _shift(w, len(groups)), "n": {stat: src}, "src": src} for w in whos]
    return effects, _out(groups + parts)


# Compound sentences whose subject is one player, read as two instructions ("Target player draws
# two cards and loses 2 life": one word "target", the same player for both, 115.3): the halves for
# scripts._clause, which reads each with the subject repeated.
_V3 = (r"draws|loses|gains|discards|mills|sacrifices|creates|puts|exiles|returns|reveals|shuffles|scries|surveils|"
       r"gets|searches")
COMPOUND = (rf"(?P<s>target player|target opponent|each player|each opponent|each of your opponents|that player) "
            rf"(?P<l>(?:{_V3}) .+?) and (?P<r>(?:{_V3}) .+)")


# -- delayed triggers & durations (agent J) --------------------------------------------------------
# Sentence forms app/rules/delayed.py needs that the grammar above doesn't read on its own. Each is
# registered as a template by the appended block of app/rules/scripts.py, so the pronoun resolver
# and the target-group bookkeeping treat the deferred effects like any others.
_PRONOUN_SACRIFICE = {"them": "them", "those tokens": "them", "those creatures": "them", "the tokens": "them",
                      "those permanents": "them", "that creature": "it", "that token": "it", "the token": "it",
                      "that permanent": "it", "that card": "it"}
_OWNER_RETURN = re.compile(r"^return (?P<o>.+?) to the battlefield(?P<t> tapped)? under (?:their|its) owner's control$")


def parse_sacrifice_pronoun(phrase: str) -> tuple[Effects, Any] | None:
    """"Sacrifice that creature / those tokens / the token": the objects an earlier instruction
    named (a pronoun for scripts.resolve_it)."""
    who = _PRONOUN_SACRIFICE.get(phrase.strip())
    return ([{"do": "sacrifice", "who": who}], None) if who else None


def parse_return_owner(text: str) -> tuple[Effects, Any] | None:
    """"Return those cards to the battlefield under their owner's control" (the singular "owner's"
    of current Oracle wording): the cards an earlier instruction moved (400.7j), each to its
    owner's side."""
    m = _OWNER_RETURN.fullmatch(text.strip())
    if not m:
        return None
    try:
        kind, key, group = ref(m["o"])
    except _Fail:
        return None
    if kind not in ("it", "them"):
        return parse_sentence(text)  # ("return all creature cards from your graveyard …": the grammar above)
    return [{"do": "return_card", "who": _who(kind, key), "to": "battlefield", "tapped": bool(m["t"]),
             "under": "owner"}], _one(group)


def parse_exile_until(phrase: str) -> tuple[Effects, Any] | None:
    """"Exile <objects> until ~ leaves the battlefield" (610.3) for any target phrase the selector
    grammar reads ("target artifact or creature an opponent controls", "up to one target nonland
    permanent …"). Not a pronoun: "exile that card until …" may name a card in a hand, and 610.3
    returns it to its previous zone, while the engine's linked return puts it onto the
    battlefield (610.3c) — that wording stays manual."""
    try:
        kind, key, group = ref(phrase.strip())
    except _Fail:
        return None
    if kind in ("players", "self", "host", "it", "them") or not on_battlefield_only(key):
        return None  # (a card exiled from a graveyard returns there, 610.3: not the linked return)
    return [{"do": "exile_until", "who": _who(kind, key)}], _one(group)


def on_battlefield_only(key: str | None) -> bool:
    """Does the selector name only objects on the battlefield (the only ones "until ~ leaves the
    battlefield" returns to the battlefield, 610.3c)? ``key``: a selector key, or a named target
    kind ("creature", "nonland_permanent_opp", "creature_spell", …)."""
    if not key:
        return False
    if key.startswith(selectors.PREFIX):
        return set(selectors.from_key(key).zones) == {"battlefield"}
    return not key.endswith("spell") and key not in ("any", "player", "opponent")


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


# -- animation (agent A2) --------------------------------------------------------------------------
# "~ becomes a 2/2 creature with all creature types until end of turn" (Mutavault), "until end of
# turn, this land becomes a 4/4 white and blue Elemental creature with flying and vigilance"
# (Celestial Colonnade), "target land becomes a 3/3 creature that's still a land" (Lifespark
# Spellbomb), "target permanent becomes an artifact in addition to its other types until end of
# turn" (Liquimetal Coating), "each noncreature artifact you control becomes a 4/4 artifact
# creature until end of turn" (Cyberdrive Awakener), "target noncreature artifact becomes an
# artifact creature with power and toughness each equal to its mana value until end of turn"
# (Karn's Touch), "target creature loses all abilities and becomes a blue Frog with base power and
# toughness 1/1" (Turn to Frog), "it becomes an artifact creature and gains haste" (Chandra, Spark
# Hunter), "target land you control becomes an X/X Elemental creature until end of turn, where X
# is the number of Allies you control" (Vastwood Animist). The separate sentence "It's still a
# land." is ``parse_still``. Read against CR 205.1a/205.1b (types set or retained), 105.3
# (colors), 613.1d-f / 613.4b (the layers each part applies in), 611.2a (no duration: the game).
# Not read (manual): "becomes a copy …" (a copy effect, layer 1), "becomes an Aura … Attach it"
# (Licids), "if ~ is an enchantment, it becomes …" (conditions), "with ward {2}" / protection
# (keywords the engine doesn't grant), a creature type not in the CR list.
_COLOR_LETTERS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_COLOR_LIST = r"(?:white|blue|black|red|green)(?:(?:,? and |, )(?:white|blue|black|red|green))*"
_BECOME = re.compile(
    r"^(?:(?P<lead>until end of turn, )|(?P<nlead>until your next turn, ))?(?:have )?(?P<o>.+?) "
    r"(?P<lose>loses all abilities and )?becomes? "
    r"(?:a|an) (?P<desc>.+?)"
    r"(?P<addition> in addition to its other (?P<addcolors>colors and )?types)?"
    r"(?P<still> that's still an? (?:land|artifact|enchantment|planeswalker|creature))?"
    r"(?: and gains? (?:(?P<gain>[a-z ]+)|(?P<gainq>\"[^\"]*\"(?:,? and \"[^\"]*\")*)))?"
    r"(?:(?P<trail> until end of turn)|(?P<ntrail> until your next turn))?$")
_DESC = re.compile(  # (each part optional, space-separated: "legendary 8/12 green Spirit artifact creature with …")
    r"^(?P<leg>legendary)?(?: ?(?P<p>X|\d+)/(?P<t>X|\d+))?(?: ?(?P<colors>colorless|" + _COLOR_LIST + r"))?"
    r"(?: ?(?P<subs>[A-Z][\w’'-]+(?: [A-Z][\w’'-]+)*))?(?: ?(?P<kinds>(?:artifact |enchantment )?(?:creature|artifact|enchantment)))?"
    r"(?: with (?P<with>.+))?$")
_QUOTED = re.compile(r'"([^"]+)"')
STILL_A = r"it's still an? (?P<t>land|artifact|enchantment|planeswalker|creature)"
_STAT_WORDS = {"power": "power", "toughness": "toughness", "mana value": "mana_value"}


def _animation_keywords(text: str) -> list[str]:
    """"flying", "trample and haste", "vigilance, indestructible, and haste" → the keywords."""
    parts = [p.strip() for p in re.split(r",? and |, ", text) if p.strip()]
    for p in parts:
        if p not in selectors.KEYWORDS or p == "protection":
            raise _Fail
    return parts


def _with_list(text: str, out: dict[str, Any]) -> None:
    """The "with …" part: keywords, "all creature types", quoted abilities, "base power and
    toughness N/N", "power and toughness each equal to <value>"."""
    abilities = _QUOTED.findall(text)
    rest = _QUOTED.sub("", text)
    rest = re.sub(r"(?:,? and |, )\s*$", "", rest.strip())
    m = re.search(r"(?:^|,? and |, )(?:base power and toughness (?P<p>\d+)/(?P<t>\d+)|"
                  r"power and toughness each equal to (?P<eq>.+))$", rest)
    if m:
        if out.get("p") is not None:
            raise _Fail
        if m["eq"]:
            out["p"] = out["t"] = _stat(m["eq"])
        else:
            out["p"], out["t"] = int(m["p"]), int(m["t"])
        rest = rest[: m.start()]
    if re.search(r"(?:^|,? and |, )all creature types$", rest):
        out["all_creature_types"] = True
        rest = re.sub(r"(?:,? and |, )?all creature types$", "", rest)
    rest = re.sub(r"(?:,? and |, )\s*$", "", rest.strip())
    if rest:
        out["keywords"] = _animation_keywords(rest)
    if abilities:
        out["abilities"] = abilities


def parse_become(text: str) -> tuple[Effects, Any] | None:
    """One "… becomes a …" sentence → ([become effect, (grant)], target) or None."""
    try:
        return _become(text.strip())
    except _Fail:
        return None


def _become(text: str) -> tuple[Effects, Any]:
    from app.rules.creature_types import CREATURE_TYPES

    text, rider = _with_rider(text)
    m = _BECOME.fullmatch(text)
    if m is None:
        raise _Fail
    d = _DESC.fullmatch(m["desc"])
    if d is None:
        raise _Fail
    kind, key, group = ref(m["o"])
    if kind == "players":
        raise _Fail
    who = _who(kind, key)
    kinds = (d["kinds"] or "").split()
    types = [k.capitalize() for k in kinds]
    subs = (d["subs"] or "").split()
    if any(s not in CREATURE_TYPES for s in subs) or ("Creature" not in types and (subs or d["p"])
                                                       and types):
        raise _Fail  # (not a creature type; a P/T or creature type for something that isn't a creature)
    if not types and not subs:
        raise _Fail
    e: dict[str, Any] = {"do": "become", "who": who, "types": types}
    if m["addition"] or m["still"] or types == ["Artifact", "Creature"]:
        e["retain"] = True  # 205.1b
    if subs:
        # 205.1b: "in addition to its other types" / "that's still a …" retain every prior subtype
        # (the creature types named are added); "[creature type] artifact creature" or a plain
        # "becomes a … creature" replaces its creature types (205.1a/205.1b last sentence)
        e["add_creature_types" if (m["addition"] or m["still"]) else "creature_types"] = subs
    if d["leg"]:
        e["legendary"] = True
    if d["colors"]:
        colors = [] if d["colors"].strip() == "colorless" else \
            [_COLOR_LETTERS[c] for c in re.split(r",? and |, ", d["colors"].strip())]
        if m["addcolors"]:
            e["add_colors"] = colors
        else:
            e["colors"] = colors
    if d["p"]:
        e["p"] = _apply(_amount(d["p"]), rider) if d["p"] == "X" else int(d["p"])
        e["t"] = _apply(_amount(d["t"]), rider) if d["t"] == "X" else int(d["t"])
    elif rider is not None:
        raise _Fail
    if d["with"]:
        _with_list(d["with"], e)
    if m["lose"]:
        e["lose_abilities"] = True
    if m["lead"] or m["trail"]:
        e["duration"] = "end_of_turn"
    elif m["nlead"] or m["ntrail"]:
        e["duration"] = "next_turn"  # 611.2a; ends as its controller's next turn begins (500.4, app/rules/delayed.py)
    else:
        e["duration"] = "permanent"  # 611.2a
    out: Effects = [e]
    if m["gain"]:
        if e["duration"] != "end_of_turn":
            raise _Fail
        out.append({"do": "grant", "who": who, "keywords": _animation_keywords(m["gain"])})
    if m["gainq"]:  # -- quoted grants (wave 2D) -- "… becomes a Bear creature in addition to its other types and gains "…""
        e["abilities"] = [*e.get("abilities", []), *_QUOTED.findall(m["gainq"])]  # (the same layer-6 effect, 613.6)
    return out, _one(group)


BASE_PT = (r"(?:(?P<lead>until end of turn|until your next turn), )?(?P<o>.+?) (?:has|have) base power and toughness "
           r"(?P<p>\d+)/(?P<t>\d+)(?: (?P<trail>until end of turn|until your next turn))?")


def parse_base_pt(m: re.Match[str]) -> tuple[Effects, Any]:
    """"Target creature has base power and toughness 3/3 until end of turn" (Restless Vinestalk):
    layer 7b only (613.4b); nothing else about it changes. With no duration it lasts the game (611.2a)."""
    if m["lead"] and m["trail"]:
        raise _Fail
    kind, key, group = ref(m["o"])
    if kind == "players":
        raise _Fail
    when = m["lead"] or m["trail"] or ""
    duration = {"until end of turn": "end_of_turn", "until your next turn": "next_turn"}.get(when, "permanent")
    return [{"do": "become", "who": _who(kind, key), "types": [], "p": int(m["p"]), "t": int(m["t"]),
             "duration": duration}], _one(group)


def parse_still(m: re.Match[str]) -> tuple[Effects, Any]:
    """"It's still a land.": the sentence before it retains the object's types (205.1b)."""
    return [{"do": "still_a", "type": m["t"].capitalize()}], None
