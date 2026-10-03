"""Conditions as data ("if you control a Forest", "if you have 5 or less life", "if you attacked this
turn"): parsed from Oracle wording, evaluated against the table. Used by intervening-if triggers
(CR 603.4: checked when the ability triggers and again as it resolves) and by "If …, [effect]"
sentences (608.2c) — including the "… instead" and "Otherwise, …" forms app/rules/scripts.py builds
on them.

A condition is one of

* ``{"value": <value>, "op": ">=" | "<=" | "==", "n": int}`` — a quantity (see app/rules/values.py)
  compared with a number (``"per_opponent": True``: one opponent must have that many, not all of
  them together);
* ``{"versus": {"value": <value>, "op": ">" | "<" | ">=" | "<="}}`` — "an opponent has more life than
  you": some one opponent's quantity compared with yours;
* ``{"succeeded": <binding>}`` — an optional payment of this resolution was made in full ("If you
  do", app/rules/context.py); ``{"flag": <binding>}`` — an earlier condition of this resolution was
  true (an "instead" / "Otherwise" clause reads the verdict the condition was given once, 608.2c);
  either ``"negate": True`` ("If you don't");
* ``{"all": [...]}`` / ``{"any": [...]}`` / ``{"not": c}`` — "and", "or" and "isn't";
* ``{"turn": "yours"}`` — it's your turn (the ability's controller's);
* ``{"status": "monarch" | "initiative" | "city_blessing"}`` — you have that designation;
* ``{"history": <kind>, …}`` — what happened earlier this turn (or ``"last": True``: the turn before;
  608.2i: such an effect looks back in time): you attacked (508.1), creatures died (700.4), a
  permanent left the battlefield under your control, life gained / lost, cards drawn, spells cast,
  cards left your graveyard, you descended (a permanent card went into it, 700.11) (app/rules/history.py);
* ``{"object": <who>, "is": <selector key>}`` / ``{"object": <who>, "test": "tapped" | …}`` — the
  object an effect refers to ("it", "that creature", "~") is / was a … (608.2h: as it is, or as it
  last existed once it left; only read where the ability has those objects: ``parse(…, objects=True)``).

:func:`parse` returns None for wordings it doesn't read (the ability then stays manual).
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.rules import selectors, values

if TYPE_CHECKING:
    from app.rules.plan import Plan

Condition = dict[str, Any]
_N = values.NUMBERS | {"no": 0}
_OPS = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b, "==": lambda a, b: a == b,
        ">": lambda a, b: a > b, "<": lambda a, b: a < b}


def _num(word: str) -> int | None:
    w = word.lower()
    return int(w) if w.isdigit() else _N.get(w)


def _count(phrase: str, controller: str) -> str | None:
    sel = selectors.parse(f"{phrase} {controller}")
    return sel.key() if sel is not None and sel.player is None else None


def parse(text: str, *, objects: bool = False) -> Condition | None:
    """A condition from its wording. ``objects``: also read conditions about an object the ability
    refers to ("it's a land card", "~ is tapped") — only for wording inside an ability's effects or
    trigger, which has those objects (statics and restrictions don't)."""
    t = text.strip().rstrip(",").replace("’", "'")
    found = _parse_one(t, objects)
    if found is not None:
        return found
    return _compound(t, objects)


def _compound(t: str, objects: bool) -> Condition | None:
    """"X and Y" / "X or Y" where each side is a condition by itself ("you control a Desert or there
    is a Desert card in your graveyard"), and "you control an artifact and an enchantment" (one
    subject for both). An "and" inside a noun phrase that doesn't split into conditions stays whole."""
    m = re.fullmatch(r"you control (?P<a>(?:a|an) .+?) (?P<j>and|or) (?P<b>(?:a|an) .+)", t)
    if m:
        parts = [_parse_one(f"you control {m[k]}", objects) for k in ("a", "b")]
        if all(p is not None for p in parts):
            return {"all" if m["j"] == "and" else "any": parts}
    for joiner in (" and ", " or "):
        for piece in re.finditer(re.escape(joiner), t):
            left, right = t[: piece.start()], t[piece.end():]
            a, b = parse(left, objects=objects), parse(right, objects=objects)
            if a is not None and b is not None:
                return {"all" if joiner == " and " else "any": [a, b]}
    return None


# -- the wordings ---------------------------------------------------------------------------------------
_CTRL = re.compile(r"(?P<who>you|an opponent) (?P<neg>don't |doesn't )?controls? "
                   r"(?P<q>a|an|another|no|\w+ or more|at least \w+) (?P<sel>.+)")
_LIFE = re.compile(r"you have (?:(?P<n>\w+) or (?P<cmp>less|more|fewer|greater)|at least (?P<least>\w+)) life")
_HAND = re.compile(r"you have (?:(?P<no>no)|(?P<n>\w+) or (?P<cmp>more|fewer|less)) cards in (?:your )?hand")
_YOUR_TURN = re.compile(r"it(?:'s| is) (?P<neg>not |n't )?your turn|it isn't your turn|it(?:'s| is) an opponent's turn")
_STATUS = {"you're the monarch": "monarch", "you are the monarch": "monarch", "you have the initiative": "initiative",
           "you have the city's blessing": "city_blessing"}
_THIS_TURN = r"(?P<when>this|last) turn"
_DIFFERENT_POWERS = re.compile(r"you control (?P<n>\w+) or more creatures with different powers")
_TOTAL_POWER = re.compile(r"creatures you control have total power (?P<n>\w+) or greater")
_GRAVEYARD = re.compile(r"there(?:'s| is| are) (?:(?P<a>a|an)|(?P<n>\w+) or more) (?P<sel>.+? in your graveyard)")
_GRAVEYARD_ARE = re.compile(r"(?P<n>\w+) or more (?P<sel>.+?) (?:are|is) in your graveyard")  # "seven or more cards are in your graveyard"
_GRAVEYARD_TYPES = re.compile(r"there are (?P<n>\w+) or more card types among cards in your graveyard")
_NONE_ON_BATTLEFIELD = re.compile(r"(?:there are )?no (?P<sel>[\w' -]+?)(?: are)? on the battlefield")
_OBJECT_STAT = re.compile(r"(?P<who>its|that creature's|that permanent's|that card's|~'s) (?P<stat>power|toughness|mana value) "
                          r"(?:is|was) (?P<n>\w+) or (?P<cmp>less|greater|more|fewer)")
_X_IS = re.compile(r"x is (?P<n>\w+)(?: or (?P<cmp>more|greater|less|fewer))?", re.IGNORECASE)
_VERSUS = re.compile(r"an opponent (?:(?P<controls>controls)|has) more (?P<what>.+?) than you")
_COMMANDER = re.compile(r"you control (?P<which>your commander|a commander)")
# "it's a land card", "that creature is a Human", "~ is an enchantment", "it was a creature card"
_OBJECT_WORDS = {"it": "it", "~": "self", "that creature": "it", "that permanent": "it", "that card": "it",
                 "that land": "it", "that token": "it", "that artifact": "it"}
_OBJECT = re.compile(r"(?P<who>it|~|that (?:creature|permanent|card|land|token|artifact)) "
                     r"(?P<verb>is|was|isn't|wasn't|is not|was not) (?P<what>.+)")
_STATES = {"tapped": "tapped", "untapped": "untapped", "attacking": "attacking", "blocking": "blocking"}
# -- counters (wave 5H) -- "if it had counters on it", "if it had a +1/+1 counter on it", "if ~ has counters on it",
# "if it doesn't have an indestructible counter on it": the object's counters as it is, or as it last existed
# (603.10a, 122.2: they cease to exist as it leaves)
_HAD_COUNTERS = re.compile(r"(?P<who>it|~|that creature|that permanent) (?:had|has|(?P<neg>doesn't have|didn't have)) "
                           r"(?:(?:a|an|one or more) )?(?:(?!no |any )(?P<k>\+1/\+1|-1/-1|[a-z]+) )?"
                           r"counters? on (?:it|them|~|him|her)")
# -- refused modal/conditional (wave 3R1) -- an ability the object has (a characteristic, 109.3: as it is, or as it
# last existed, 608.2h — granted ones included). Keyword abilities only; "protection" (which quality?) isn't read.
_HAS_KEYWORD = re.compile(r"(?P<who>it|~|that (?:creature|permanent|card)) has (?P<kw>flying|reach|haste|trample|deathtouch|"
                          r"lifelink|menace|vigilance|first strike|double strike|hexproof|indestructible|defender|infect|"
                          r"toxic|wither|flash|madness|flashback|shroud|cycling)")


def _cmp(word: str | None) -> str:
    return "<=" if word in ("less", "fewer") else ">="


def _parse_one(t: str, objects: bool) -> Condition | None:
    # -- combat (wave 5C) -- "it's the first combat phase of the turn" (500.8: additional ones may follow), "it's your
    # main phase" (505.1)
    if t in ("it's the first combat phase of the turn", "it is the first combat phase of the turn"):
        return {"combat_phase": "first"}
    if t in ("it's your main phase", "it is your main phase"):
        return {"main_phase": "yours"}
    # "you control a Forest", "you control two or more Islands", "you control another Elf",
    # "you control no creatures", "you don't control a …", "an opponent controls a …"
    m = _DIFFERENT_POWERS.fullmatch(t)
    if m:  # "you control three or more creatures with different powers"
        n = _num(m["n"])
        key = _count("creatures", "you control")
        if n is None or key is None:
            return None
        return {"value": {"distinct": "powers", "among": key}, "op": ">=", "n": n}
    m = _COMMANDER.fullmatch(t)
    if m:  # "you control your commander" (Lieutenant): a commander you own (903.3), on the battlefield under your control
        commanders = selectors.Selector(commander=True, controller="you", owner="you" if m["which"] == "your commander" else None)
        return {"value": {"count": commanders.key()}, "op": ">=", "n": 1}
    m = _CTRL.fullmatch(t)
    if m:
        q = m["q"]
        other = q == "another"
        if q in ("a", "an", "another"):
            n, op = 1, ">="
        elif q == "no":
            n, op = 0, "=="
        else:
            word = q.split()[2] if q.startswith("at least") else q.split()[0]
            got = _num(word)
            if got is None:
                return None
            n, op = got, ">="
        if m["neg"]:
            if op != ">=" or n != 1:
                return None
            n, op = 0, "=="
        key = _count(("another " if other else "") + m["sel"], "you control" if m["who"] == "you" else "an opponent controls")
        if not key:
            return None
        out: Condition = {"value": {"count": key}, "op": op, "n": n}
        if m["who"] == "an opponent":
            out["per_opponent"] = True  # one opponent must have that many, not all of them together
        return out
    # "you have 5 or less life", "you have 30 or more life", "you have at least 10 life"
    m = _LIFE.fullmatch(t)
    if m:
        life = _num(m["n"] or m["least"])
        if life is None:
            return None
        return {"value": {"life": "you"}, "op": "<=" if m["cmp"] in ("less", "fewer") else ">=", "n": life}
    # "you have no cards in hand", "you have N or more cards in hand"
    m = _HAND.fullmatch(t)
    if m:
        if m["no"]:
            return {"value": {"hand": "you"}, "op": "==", "n": 0}
        cards = _num(m["n"])
        if cards is None:
            return None
        return {"value": {"hand": "you"}, "op": ">=" if m["cmp"] == "more" else "<=", "n": cards}
    # -- conditional / instead clauses (wave 1B) --------------------------------------------------------
    m = _YOUR_TURN.fullmatch(t)
    if m:  # 500.1: whose turn it is (an opponent's turn is any turn that isn't yours: every other player is one)
        mine: Condition = {"turn": "yours"}
        return {"not": mine} if (m["neg"] or t.startswith("it isn't") or "opponent's" in t) else mine
    if t in _STATUS:
        return {"status": _STATUS[t]}
    if t == "you have a full party":  # -- refused modal/conditional (wave 3R1) -- 700.8c: four creatures in your party
        return {"value": {"party": "you"}, "op": ">=", "n": 4}
    found = _history(t)
    if found is not None:
        return found
    m = _TOTAL_POWER.fullmatch(t)
    if m:  # "creatures you control have total power 8 or greater"
        n = _num(m["n"])
        key = _count("creatures", "you control")
        if n is None or key is None:
            return None
        return {"value": {"sum": "power", "of": key}, "op": ">=", "n": n}
    m = _GRAVEYARD_TYPES.fullmatch(t)
    if m:  # delirium: "there are four or more card types among cards in your graveyard" (205.2a)
        n = _num(m["n"])
        amount = values.parse_count("card types among cards in your graveyard")
        return {"value": amount, "op": ">=", "n": n} if n is not None and amount is not None else None
    # -- recursion & tutors (wave 4M) -- "you have four or more creature cards in your graveyard" (Oversold Cemetery):
    # the same count as "there are four or more creature cards in your graveyard"
    m = _GRAVEYARD.fullmatch(re.sub(r"^you have (?=(?:an?|\w+ or more) .+? in your graveyard$)", "there are ", t)) \
        or _GRAVEYARD_ARE.fullmatch(t)
    if m:  # "there are seven or more cards in your graveyard", "there is a Desert card in your graveyard"
        n = 1 if m.groupdict().get("a") else _num(m["n"] or "")
        in_graveyard = selectors.parse(m["sel"] if "in your graveyard" in m["sel"] else m["sel"] + " in your graveyard")
        if n is None or in_graveyard is None or in_graveyard.player is not None or in_graveyard.zones != ("graveyard",):
            return None
        return {"value": {"count": in_graveyard.key()}, "op": ">=", "n": n}
    m = _NONE_ON_BATTLEFIELD.fullmatch(t)
    if m:  # "no creatures are on the battlefield" (Pestilence): none of them, whoever controls them
        on_battlefield = selectors.parse(m["sel"])
        if (on_battlefield is None or on_battlefield.player is not None or on_battlefield.zones != ("battlefield",)
                or on_battlefield.controller is not None):
            return None
        return {"value": {"count": on_battlefield.key()}, "op": "==", "n": 0}
    m = _X_IS.fullmatch(t)
    if m:  # 107.3: "X is five or more" (the X this spell was cast with)
        n = _num(m["n"])
        if n is None:
            return None
        return {"value": {"x": 1}, "op": "==" if not m["cmp"] else ("<=" if m["cmp"] in ("less", "fewer") else ">="), "n": n}
    m = _VERSUS.fullmatch(t)
    if m:  # "an opponent controls more lands than you" / "has more life than you"
        what = m["what"]
        quantity: Any
        if m["controls"]:
            key = _count(what, "you control")
            quantity = {"count": key} if key else None
        else:
            quantity = {"life": "you"} if what == "life" else {"hand": "you"} if what == "cards in hand" else None
        return {"versus": {"value": quantity, "op": ">"}} if quantity is not None else None
    found = designation_condition(t)  # -- counters & designations (wave 3E) --
    if found is not None:
        return found
    if objects:
        found = _cast_how(t)  # -- refused modal/conditional (wave 3R1) --
        if found is not None:
            return found
        return _object(t)
    return None


# -- counters & designations (wave 3E) --------------------------------------------------------------
# "an opponent has three or more poison counters" (corrupted; one opponent, 122.1f), "you have N or more
# experience counters", "you have no rad counters"; "there is no monarch" / "an opponent is the
# monarch" (725), "you've completed a dungeon" (309.7), "it's day / night" (731).
_HAS_COUNTERS = re.compile(r"(?P<who>you|an opponent) (?:has|have) (?:(?P<no>no)|(?P<a>a|an|one or more)|(?P<n>\w+) or more) "
                           r"(?P<kind>poison|experience|rad|energy) counters?")
_DESIGNATIONS = {"there is no monarch": "no_monarch", "an opponent is the monarch": "opponent_monarch",
                 "you're not the monarch": "not_monarch", "you aren't the monarch": "not_monarch",
                 "you don't have the initiative": "not_initiative", "you've completed a dungeon": "completed_dungeon",
                 "you have completed a dungeon": "completed_dungeon",
                 "it's day": "day", "it's night": "night", "it's neither day nor night": "neither_day_nor_night"}


def designation_condition(t: str) -> Condition | None:
    m = _HAS_COUNTERS.fullmatch(t)
    if m:
        n = 0 if m["no"] else 1 if m["a"] else _num(m["n"] or "")
        if n is None:
            return None
        out: Condition = {"value": {"player_counters": m["kind"]}, "op": "==" if m["no"] else ">=", "n": n}
        if m["who"] == "an opponent":
            out["per_opponent"] = True  # one opponent must have that many (not all of them together)
        return out
    if t in _DESIGNATIONS:
        return {"status": _DESIGNATIONS[t]}
    return None
# -- end counters & designations (wave 3E) --


_HISTORY_PATTERNS: list[tuple[re.Pattern[str], Any]] = []


def _when(m: re.Match[str]) -> dict[str, Any]:
    return {"last": True} if m.groupdict().get("when") == "last" else {}


def _history_pattern(pattern: str):  # type: ignore[no-untyped-def]
    def register(fn):  # type: ignore[no-untyped-def]
        _HISTORY_PATTERNS.append((re.compile(pattern), fn))
        return fn
    return register


@_history_pattern(r"you attacked(?: with a creature)? this turn")
def _attacked(m: re.Match[str]) -> Condition:
    return {"history": "attacked"}  # 508.1: declared attackers; 508.4: a creature put onto the battlefield attacking never "attacked"


@_history_pattern(r"you (?:didn't|did not) attack(?: with a creature)? this turn")
def _not_attacked(m: re.Match[str]) -> Condition:
    return {"not": {"history": "attacked"}}


@_history_pattern(r"(?:a creature|(?P<n>\w+) or more creatures) died(?P<mine> under your control)? this turn")
def _died(m: re.Match[str]) -> Condition | None:
    n = 1 if m["n"] is None else _num(m["n"])
    return None if n is None else {"history": "died", "who": "you" if m["mine"] else "any", "n": n}


@_history_pattern(r"a creature you controlled died this turn")
def _died_mine(m: re.Match[str]) -> Condition:
    return {"history": "died", "who": "you", "n": 1}


@_history_pattern(r"a permanent (?:left the battlefield under your control|you controlled left the battlefield) this turn")
def _left(m: re.Match[str]) -> Condition:
    return {"history": "left", "who": "you"}  # revolt (700.4: leaves the battlefield = moves to another zone)


@_history_pattern(r"you(?:'ve)? gained (?:life|(?P<n>\w+) or more life) this turn")
def _gained(m: re.Match[str]) -> Condition | None:
    n = _num(m["n"]) if m["n"] else 1
    return None if n is None else {"history": "gained", "n": n}


@_history_pattern(rf"(?P<who>you(?:'ve)?|an opponent(?: has)?|a player(?: has)?) lost (?:life|(?P<n>\w+) or more life) {_THIS_TURN}")
def _lost(m: re.Match[str]) -> Condition | None:
    n = _num(m["n"]) if m["n"] else 1
    who = "you" if m["who"].startswith("you") else "opponent" if m["who"].startswith("an opponent") else "any"
    return None if n is None else {"history": "lost", "who": who, "n": n, **_when(m)}


@_history_pattern(r"you(?:'ve)? drawn (?P<n>\w+) or more cards this turn")
def _drew(m: re.Match[str]) -> Condition | None:
    n = _num(m["n"])
    return None if n is None else {"history": "drew", "n": n}


@_history_pattern(r"you(?:'ve)? cast (?P<n>\w+) or more spells this turn")
def _spells(m: re.Match[str]) -> Condition | None:
    n = _num(m["n"])
    return None if n is None else {"history": "spells", "n": n}


@_history_pattern(r"you(?: haven't| didn't|'ve not| have not| did not) cast (?:a|any) spells? this turn")
def _no_spells(m: re.Match[str]) -> Condition:
    return {"not": {"history": "spells", "n": 1}}


@_history_pattern(r"a card left your graveyard this turn")
def _left_graveyard(m: re.Match[str]) -> Condition:
    return {"history": "left_graveyard"}


@_history_pattern(r"you descended this turn")
def _descended(m: re.Match[str]) -> Condition:
    return {"history": "descended", "n": 1}  # 700.11: a permanent card was put into your graveyard from anywhere


# -- refused modal/conditional (wave 3R1) -- celebration and friends (608.2i: as they were when they entered)
@_history_pattern(r"(?P<q>a|an|another|\w+ or more) (?P<sel>.+?) entered the battlefield under your control this turn")
def _entered(m: re.Match[str]) -> Condition | None:
    q = m["q"]
    n = 1 if q in ("a", "an", "another") else _num(q.split()[0])
    sel = selectors.parse(m["sel"])
    if n is None or sel is None or sel.player is not None or sel.controller is not None or sel.owner is not None \
            or sel.zones != ("battlefield",) or sel.other or sel.tapped is not None or sel.attacking or sel.blocking:
        return None
    return {"history": "entered", "sel": sel.key(), "n": n, **({"other": True} if q == "another" else {})}


@_history_pattern(r"~ entered this turn")
def _entered_self(m: re.Match[str]) -> Condition:
    return {"history": "entered_self"}  # this object entered the battlefield this turn (a new object if it left, 400.7)
# -- end refused modal/conditional (wave 3R1) --


# -- this-turn history (wave 4D) -- what players did this turn (app/rules/history.py reads TurnLog; 608.2i: the objects
# as they were then). A selector the history can't check (keywords, tapped, who controls it now …) isn't read.
_WHO_DID = r"(?P<who>you(?:'ve| have)?|an opponent(?: has)?|a player(?: has)?|one or more (?:of your )?opponents(?: have)?)"
_Q = r"(?P<q>a|an|another|no|one or more|\w+ or more)"


def _who(m: re.Match[str]) -> str:
    w = m["who"]
    return "you" if w.startswith("you") else "any" if w.startswith("a player") else "opponent"


def _q(q: str) -> tuple[int, str] | None:
    """"a" / "one or more" (at least one), "two or more", "no" (none)."""
    if q in ("a", "an", "another", "one or more"):
        return 1, ">="
    if q == "no":
        return 0, "=="
    n = _num(q.split()[0])
    return (n, ">=") if n is not None else None


def _history_sel(phrase: str, zone: str) -> str | None:
    """A selector the recorded characteristics can answer: types, subtypes, supertypes, colors, mana value, token."""
    from app.rules import history

    sel = selectors.parse(phrase)
    if sel is None or not history.note_selector_ok(sel) or sel.zones != (zone,):
        return None
    return sel.key()


@_history_pattern(r"~ (?P<neg>didn't |did not )?attack(?:ed)? this turn")
def _self_attacked(m: re.Match[str]) -> Condition:
    found: Condition = {"history": "self_attacked", "object": "self"}  # 508.1: this object was declared as an attacker this turn
    return {"not": found} if m["neg"] else found


@_history_pattern(r"~ (?:didn't|did not) enter the battlefield this turn")
def _self_not_entered(m: re.Match[str]) -> Condition:
    return {"not": {"history": "entered_self", "object": "self"}}  # ("object": what "it" after it names, 608.2c)


@_history_pattern(r"~ dealt (?P<kind>combat )?damage to an opponent this turn")
def _self_dealt(m: re.Match[str]) -> Condition:
    return {"history": "damage", "who": "opponent", "n": 1, "by_self": True, "object": "self", **({"combat": True} if m["kind"] else {})}


@_history_pattern(r"(?P<q>a|an|one or more|\w+ or more) (?P<sel>.+? cards?) (?:was|were) put into your graveyard from anywhere this turn")
def _to_graveyard(m: re.Match[str]) -> Condition | None:
    q = _q(m["q"])
    sel = selectors.parse(m["sel"] + " in your graveyard")
    from app.rules import history

    if q is None or sel is None or sel.zones != ("graveyard",) or sel.zone_owner != "you" \
            or not history.note_selector_ok(replace(sel, zone_owner=None, card=False)):
        return None
    return {"history": "graveyard_cards", "sel": sel.key(), "n": q[0]}  # (cards: a token never is one, 111.1)


@_history_pattern(r"you(?:'ve| have)? created (?:a token|(?P<n>\w+) or more tokens) this turn")
def _tokens(m: re.Match[str]) -> Condition | None:
    n = _num(m["n"]) if m["n"] else 1
    return None if n is None else {"history": "tokens", "who": "you", "n": n}  # 111.2


@_history_pattern(r"you attacked with (?P<n>\w+) or more creatures this turn")
def _attackers(m: re.Match[str]) -> Condition | None:
    n = _num(m["n"])
    return None if n is None else {"history": "attackers", "n": n}  # 508.1: creatures declared as attackers, any combat


@_history_pattern(r"no creatures attacked this turn")
def _nobody_attacked(m: re.Match[str]) -> Condition:
    return {"not": {"history": "attacked", "who": "any"}}


@_history_pattern(r"you(?:'ve| have)? gained (?P<j>and|or) lost life this turn")
def _gained_lost(m: re.Match[str]) -> Condition:
    both = [{"history": "gained", "n": 1}, {"history": "lost", "who": "you", "n": 1}]  # (not the net change)
    return {"all" if m["j"] == "and" else "any": both}


@_history_pattern(rf"{_WHO_DID} cast {_Q} (?P<sel>.+?)(?P<hand> from (?:your|their) hand)? this turn")
def _cast_this_turn(m: re.Match[str]) -> Condition | None:
    q = _q(m["q"])
    sel = m["sel"].replace(" and/or ", " or ")
    sel = re.sub(r"^(instant|sorcery) and (instant|sorcery) spells$", r"\1 or \2 spells", sel)
    key = _history_sel(sel, "stack")
    if q is None or key is None or (m["q"] == "another" and _who(m) != "you"):
        return None
    out: Condition = {"history": "cast", "who": _who(m), "sel": key, "n": q[0], "op": q[1]}
    if m["q"] == "another":
        out["other"] = True  # (not the spell this ability is part of, nor the spell its source permanent was)
    if m["hand"]:
        out["from"] = "hand"
    return out


@_history_pattern(r"you(?: haven't| didn't|'ve not| have not| did not) cast (?:a|an|any) (?P<sel>.+?)(?P<hand> from your hand)? this turn")
def _not_cast_this_turn(m: re.Match[str]) -> Condition | None:
    key = _history_sel(m["sel"], "stack")
    if key is None:
        return None
    return {"not": {"history": "cast", "who": "you", "sel": key, "n": 1, "op": ">=", **({"from": "hand"} if m["hand"] else {})}}


@_history_pattern(r"you(?:'ve| have)? cast both (?:a|an) (?P<a>.+? spell) and (?:a|an) (?P<b>.+? spell) this turn")
def _cast_both(m: re.Match[str]) -> Condition | None:
    keys = [_history_sel(m[k], "stack") for k in ("a", "b")]
    if None in keys:
        return None
    return {"all": [{"history": "cast", "who": "you", "sel": k, "n": 1, "op": ">="} for k in keys]}


@_history_pattern(rf"{_WHO_DID} discarded (?:a card|(?P<n>\w+) or more cards) this turn")
def _discarded(m: re.Match[str]) -> Condition | None:
    n = _num(m["n"]) if m["n"] else 1
    return None if n is None else {"history": "facts", "kind": "discard", "who": _who(m), "n": n}  # 701.9a


@_history_pattern(rf"you(?:'ve| have)? sacrificed {_Q} (?P<sel>.+?) this turn")
def _sacrificed(m: re.Match[str]) -> Condition | None:
    q = _q(m["q"])
    key = _history_sel(m["sel"], "battlefield")
    if q is None or key is None or m["q"] in ("another", "no"):
        return None
    return {"history": "facts", "kind": "sacrifice", "who": "you", "sel": key, "n": q[0]}  # 701.21a


@_history_pattern(r"you(?:'ve| have)? (?P<what>scried or surveilled|surveilled|scried) this turn")
def _looked(m: re.Match[str]) -> Condition:
    kinds = ["scry", "surveil"] if "or" in m["what"] else ["surveil"] if m["what"] == "surveilled" else ["scry"]
    return {"any": [{"history": "facts", "kind": k, "who": "you", "n": 1} for k in kinds]}  # 701.22, 701.25


@_history_pattern(r"(?:an opponent|one or more opponents) (?:was|were|has been|have been) dealt (?:(?P<n>\w+) or more )?"
                  r"(?P<kind>combat |noncombat )?damage(?P<legend> by a legendary creature)? this turn")
def _opponent_dealt(m: re.Match[str]) -> Condition | None:
    n = _num(m["n"]) if m["n"] else 1
    if n is None:
        return None
    out: Condition = {"history": "damage", "who": "opponent", "n": n}
    if m["kind"]:
        out["combat"] = m["kind"] == "combat "
    if m["legend"]:  # (Blitzball: whoever controls it)
        out["source"] = {"types": ["Creature"], "supertypes": ["Legendary"]}
    return out


@_history_pattern(r"(?P<q>a|an|one or more) (?P<counter>\S+) counters? (?:was|were) put on (?:a|an) (?P<sel>.+?) "
                  r"(?:under your control|you control) this turn")
def _counters_put(m: re.Match[str]) -> Condition | None:
    key = _history_sel(m["sel"], "battlefield")
    if key is None or m["counter"] not in ("+1/+1", "-1/-1", "loyalty", "oil", "lore", "shield", "stun"):
        return None
    return {"history": "facts", "kind": "counters", "who": "you", "counter": m["counter"], "sel": key, "n": 1}


@_history_pattern(r"you(?:'ve| have)? committed a crime this turn")
def _crime(m: re.Match[str]) -> Condition:
    return {"history": "facts", "kind": "crime", "who": "you", "n": 1}  # 700.13


@_history_pattern(r"this is the (?P<nth>first|second|third|fourth|fifth) time this ability has resolved this turn")
def _resolution(m: re.Match[str]) -> Condition:
    return {"history": "resolution", "n": ["first", "second", "third", "fourth", "fifth"].index(m["nth"]) + 1}


@_history_pattern(r"you(?:'ve| have)? played a land this turn")
def _played_land(m: re.Match[str]) -> Condition:
    return {"history": "lands", "n": 1}  # 305.1 / 701.18a: played, not put onto the battlefield


@_history_pattern(r"you(?: didn't| did not| haven't| have not) play(?:ed)? a land this turn")
def _no_land(m: re.Match[str]) -> Condition:
    return {"not": {"history": "lands", "n": 1}}


@_history_pattern(r"you had (?P<q>a|an|another|\w+ or more) (?P<sel>.+?) enter the battlefield under your control this turn")
def _had_enter(m: re.Match[str]) -> Condition | None:
    return _entered(m)


@_history_pattern(r"(?P<q>a|an|another|\w+ or more) (?P<sel>.+?) entered the battlefield under an opponent's control this turn")
def _entered_opponent(m: re.Match[str]) -> Condition | None:
    found = _entered(m)
    return None if found is None or found.get("other") else {**found, "who": "opponent"}


@_history_pattern(rf"{_Q} (?P<sel>.+?) (?P<verb>died|left the battlefield|(?:was|were) put into (?P<gy>a|your) graveyard from the battlefield)"
                  r"(?P<whose> under your control| under an opponent's control)? this turn")
def _departed(m: re.Match[str]) -> Condition | None:
    q = _q(m["q"])
    sel = m["sel"]
    key = _history_sel(sel, "battlefield")
    if q is None or key is None:
        return None
    out: Condition = {"history": "departed", "sel": key, "n": q[0], "op": q[1],
                      "died": not m["verb"].startswith("left")}  # 700.4: dies = put into a graveyard from the battlefield
    if m["whose"]:
        out["who"] = "you" if "your" in m["whose"] else "opponent"
    if m["q"] == "another":
        out["other"] = True
    if m["gy"] == "your":
        out["owner"] = "you"  # (a permanent goes to its owner's graveyard, 400.3)
    return out
# -- end this-turn history (wave 4D) --


def _history(t: str) -> Condition | None:
    for pattern, build in _HISTORY_PATTERNS:
        m = pattern.fullmatch(t)
        if m:
            return build(m)
    return None


def _object(t: str) -> Condition | None:
    """"It's a land card", "that creature is a Human", "~ is an enchantment", "it isn't a creature",
    "~ is tapped": a test of the object the ability refers to (``"it"``: bound by scripts.resolve_it
    to its antecedent). Only characteristics are read of any referred object (608.2h: as it is, or as
    it last existed); physical state (tapped, attacking) only of the source itself."""
    m = _OBJECT_STAT.fullmatch(t)
    if m:  # "its mana value was 3 or less", "its power is 4 or greater"
        n = _num(m["n"])
        if n is None:
            return None
        return {"object": "self" if m["who"] == "~'s" else "it", "stat": m["stat"].replace(" ", "_"),
                "op": "<=" if m["cmp"] in ("less", "fewer") else ">=", "n": n}
    m = _HAD_COUNTERS.fullmatch(t)  # -- counters (wave 5H) --
    if m:
        out_c: Condition = {"object": _OBJECT_WORDS[m["who"]], "counters": m["k"] or "*"}
        return {"not": out_c} if m["neg"] else out_c
    m = _HAS_KEYWORD.fullmatch(t)  # -- refused modal/conditional (wave 3R1) -- "if that creature has toxic"
    if m:
        return {"object": _OBJECT_WORDS[m["who"]], "has": m["kw"]}
    t = re.sub(r"^(it|that (?:creature|permanent|card|land|token|artifact))'s ", r"\1 is ", t)
    m = _OBJECT.fullmatch(t)
    if m is None:
        return None
    who = _OBJECT_WORDS[m["who"]]
    negate = m["verb"] in ("isn't", "wasn't", "is not", "was not")
    what = m["what"].strip()
    if what in _STATES:
        if who != "self":
            return None  # (tapped / untapped / attacking / blocking: the source's own state, never an LKI guess)
        out: Condition = {"object": who, "test": _STATES[what]}
    else:
        det = re.match(r"(?:a|an) (?P<rest>.+)", what)
        if det is None and re.fullmatch(r"(?:white|blue|black|red|green)(?: or (?:white|blue|black|red|green))*", what):
            det = re.match(r"(?P<rest>.+)", what + " permanent")  # "it's blue": a color test, on whatever it is
        sel = selectors.parse(det["rest"]) if det else None
        if (sel is None or sel.player is not None or sel.zone_owner is not None or sel.controller is not None
                or sel.owner is not None or sel.zones not in (("battlefield",), ())):
            return None  # (a test of the object's characteristics, wherever it is: no zone or player relation)
        out = {"object": who, "is": sel.key()}
    if negate:  # ("isn't": still needs the object to be there to be judged — a missing one passes no test)
        return {**out, "negate": True} if "is" in out else {"not": out}
    return out


# -- evaluation -----------------------------------------------------------------------------------------
def objects_in(cond: Condition) -> list[str]:
    """The objects a condition tests ("it" until bound, "self", "event", "target", "ref:e0")."""
    if "object" in cond:
        return [str(cond["object"])]
    out: list[str] = []
    for k in ("all", "any"):
        for c in cond.get(k, ()):
            out += objects_in(c)
    if "not" in cond:
        out += objects_in(cond["not"])
    return out


def _has_objects(cond: Condition) -> bool:
    """Does a condition read an object a pronoun names ("it")? (scripts.resolve_it binds it.)"""
    return "it" in objects_in(cond)


def bind_objects(cond: Condition, who: str) -> Condition:
    """The condition with its pronoun ("it") bound to ``who`` ("self", "event", "target", "ref:e0")."""
    if "object" in cond:
        return {**cond, "object": who} if cond["object"] == "it" else cond
    out = dict(cond)
    for k in ("all", "any"):
        if k in cond:
            out[k] = [bind_objects(c, who) for c in cond[k]]
    if "not" in cond:
        out["not"] = bind_objects(cond["not"], who)
    return out


def holds(plan: Plan, ctx: dict[str, Any], cond: Condition) -> bool:
    if "all" in cond:
        return all(holds(plan, ctx, c) for c in cond["all"])
    if "any" in cond:
        return any(holds(plan, ctx, c) for c in cond["any"])
    if "not" in cond:
        return not holds(plan, ctx, cond["not"])
    if "succeeded" in cond:  # "If you do": that payment (by its binding) was made in full (118.12)
        from app.rules import context

        ok = context.succeeded(ctx, cond["succeeded"]) or context.probe_ok(plan, ctx, cond["succeeded"])
        return not ok if cond.get("negate") else ok  # "If you don't" / "… unless … pays" (118.12a)
    if "flag" in cond:  # an earlier condition of this resolution, as it was judged once (608.2c)
        from app.rules import context

        ok = context.flag(ctx, cond["flag"])
        return not ok if cond.get("negate") else ok
    if "turn" in cond:
        return plan.state.turn.active_player == ctx["controller"]
    if "status" in cond:
        return _status(plan, ctx["controller"], cond["status"])
    if "history" in cond:
        from app.rules import history

        return history.holds(plan, ctx, cond)
    if "cast" in cond:  # -- refused modal/conditional (wave 3R1) --
        return _cast_holds(plan, ctx, cond)
    if "object" in cond:
        return _object_holds(plan, ctx, cond)
    if "versus" in cond:
        return _versus(plan, ctx, cond["versus"])
    if "combat_phase" in cond:  # -- combat (wave 5C) --
        from app.game.state import COMBAT_PHASES

        return plan.state.turn.phase in COMBAT_PHASES and plan.rules.combats == 1
    if "main_phase" in cond:  # -- combat (wave 5C) --
        return plan.state.turn.phase in ("main1", "main2") and plan.state.turn.active_player == ctx["controller"]
    v = cond["value"]
    n = cond["n"]
    if cond.get("per_opponent") and "player_counters" in v:  # (wave 3E) "an opponent has three or more poison counters"
        per = [values.evaluate(plan, {**ctx, "controller": p}, v) for p in plan.live() if p != ctx["controller"]]
        return any(_OPS[cond["op"]](x, n) for x in per)
    if cond.get("per_opponent"):
        found = selectors.candidates(plan, selectors.from_key(v["count"]), ctx["controller"], ctx.get("source_card"))
        per = [sum(1 for c in found if plan.state.cards[c].controller == p) for p in plan.live() if p != ctx["controller"]]
        # "an opponent controls two or more …" / "… controls no …": some one opponent does
        return any({">=": x >= n, "<=": x <= n, "==": x == n}[cond["op"]] for x in per)
    got = plan.state.players[ctx["controller"]].life if "life" in v else values.evaluate(plan, ctx, v)
    return {">=": got >= n, "<=": got <= n, "==": got == n}[cond["op"]]


def _status(plan: Plan, you: str, kind: str) -> bool:
    if kind == "monarch":  # 724: the monarch designation
        return plan.state.table.monarch == you
    if kind == "initiative":  # 726
        return plan.state.table.initiative == you
    if kind != "city_blessing":  # -- counters & designations (wave 3E) --
        from app.rules import designations

        return designations.status(plan, you, kind)
    return bool(plan.state.players[you].city_blessing)  # 702.131c ascend: the city's blessing


def _versus(plan: Plan, ctx: dict[str, Any], spec: dict[str, Any]) -> bool:
    """Some one opponent's quantity compared with yours ("an opponent controls more lands than you"):
    the same quantity read for each of them (as "you" of that quantity)."""
    mine = values.evaluate(plan, ctx, spec["value"])
    return any(_OPS[spec["op"]](values.evaluate(plan, {**ctx, "controller": p}, spec["value"]), mine)
               for p in plan.live() if p != ctx["controller"])


def _object_holds(plan: Plan, ctx: dict[str, Any], cond: Condition) -> bool:
    """A test of one object ("it's a land card"): its characteristics as it is now while it is still
    that object where it was, else as it last existed (608.2h); an object that can't be found
    fails the test (608.2b: a part that needs the information can't be carried out)."""
    who = cond["object"]
    if "test" in cond:
        return _self_state(plan, ctx, cond["test"])
    got = values._object(plan, ctx, who)
    if who == "event" and "is" in cond and selectors.from_key(cond["is"]).card:
        # "exile it if it's an instant or sorcery card" after "dies": the card it is now (a face-down 2/2 that died
        # is its face-up card in the graveyard, 708.9), while it is still there; else as it last existed
        from app.rules import context

        new = context.objects(plan, ctx, context.EVENT_NEW)
        if new:
            got = (plan.state.cards[new[0]], plan.ch(plan.state.cards[new[0]]))
    if got is None:
        return False
    card, ch = got
    if "counters" in cond:  # -- counters (wave 5H) -- as it is, or as it last existed (603.10a)
        kind = cond["counters"]
        return any(v > 0 for v in card.counters.values()) if kind == "*" else card.counters.get(kind, 0) > 0
    if "has" in cond:  # -- refused modal/conditional (wave 3R1) --
        return cond["has"] in ch.keywords
    if "stat" in cond:  # "its mana value was 3 or less": a characteristic, as it is or as it last existed (608.2h)
        value = values._stat_of(ch, cond["stat"])
        return value is not None and _OPS[cond["op"]](value, cond["n"])
    # "it's a land card" / "that creature is a Human": its characteristics, wherever it is (a card in
    # a library, a graveyard or exile, or a permanent as it last existed): the zone is not the test
    sel = replace(selectors.from_key(cond["is"]), zones=(card.zone.rsplit(":", 1)[-1],))
    found = selectors.matches(plan, sel, card, ch, ctx["controller"], ctx.get("source_card"))
    return not found if cond.get("negate") else found


def _self_state(plan: Plan, ctx: dict[str, Any], test: str) -> bool:
    """The source's own physical state ("~ is tapped"): as it is while it's still that object on the
    battlefield, else as it last existed there (608.2h)."""
    card = plan.state.cards.get(ctx.get("source_card") or "")
    if card is not None and card.zone.endswith(":battlefield") and plan.oid(card) == ctx.get("source_object"):
        tapped, attacking, blocking = card.tapped, card.attacking is not None, bool(card.blocking)
    else:
        snap = plan.rules.lki.get(ctx.get("source_object") or "")
        if snap is None:
            return False
        tapped, attacking, blocking = snap.tapped, snap.attacking, snap.blocking
    return {"tapped": tapped, "untapped": not tapped, "attacking": attacking, "blocking": blocking}[test]


# -- refused modal/conditional (wave 3R1): how a spell was cast -----------------------------------------
# "if you cast it [from your hand]", "if it was cast", "if this spell was cast from a graveyard", "if {R} was spent
# to cast it", "{U}{B} was spent", adamant ("at least three red mana" / "of the same color"), "five or more mana",
# addendum ("if you cast this spell during your main phase"). Read from the spell's payment record (601.2h: what
# paid the total cost; casting.record_payment), which the permanent it becomes keeps (engine.leave_stack). A copy
# was never cast (707.10): its record says so. ``{"object": "it" | "self", "cast": {...}}``: "it" is bound to its
# antecedent by scripts.resolve_it, and scripts only keeps an ability whose "it" is the source itself.
# Refused (None): snow mana ({S}: what produced the mana isn't recorded), "mana from a Treasure" (the source of the
# mana), "that spell" (the trigger's spell, whose record is gone once it resolved), "entered from your graveyard".
_CAST_SUBJECT = r"(?:it|this spell|~)"
_CAST = re.compile(rf"(?:(?P<you>you) cast (?P<who>{_CAST_SUBJECT})|(?P<who2>{_CAST_SUBJECT}) was cast)"
                   r"(?: from (?P<from>your hand|a graveyard|your graveyard|exile|your library|anywhere other than your hand))?"
                   r"(?P<main> during your main phase)?")
_SPENT_SYMBOLS = re.compile(rf"(?P<syms>(?:\{{[WUBRGC]\}})+) was spent to cast (?P<who>{_CAST_SUBJECT})")
_SPENT_COLOR = re.compile(rf"at least (?P<n>\w+) (?P<color>white|blue|black|red|green) mana was spent to cast (?P<who>{_CAST_SUBJECT})")
_SPENT_SAME = re.compile(rf"at least (?P<n>\w+) mana of the same color was spent to cast (?P<who>{_CAST_SUBJECT})")
_SPENT_TOTAL = re.compile(rf"(?P<n>\w+) or more mana was spent to cast (?P<who>{_CAST_SUBJECT})")
_COLOR_LETTER = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_FROM = {"your hand": "hand", "a graveyard": "graveyard", "your graveyard": "graveyard", "exile": "exile",
         "your library": "library", "anywhere other than your hand": "!hand"}


def _cast_who(word: str) -> str:
    return "it" if word == "it" else "self"


_NO_MANA = re.compile(r"no mana was spent to cast (?:it|that spell)")  # -- if you do (wave 5G) --


def _cast_how(t: str) -> Condition | None:
    """A condition about how the source was cast, or None."""
    if _NO_MANA.fullmatch(t):  # -- if you do (wave 5G) -- "if no mana was spent to cast it" (a cast trigger's spell)
        return {"object": "it", "cast": {"no_mana": True}}
    m = _CAST.fullmatch(t)
    if m:
        how: dict[str, Any] = {"by_you": bool(m["you"])}
        if m["from"]:
            if m["from"] == "your graveyard" and not m["you"]:
                return None
            how["from"] = _FROM[m["from"]]
        if m["main"]:
            if not m["you"]:
                return None
            how["main"] = True
        return {"object": _cast_who(m["who"] or m["who2"]), "cast": how}
    m = _SPENT_SYMBOLS.fullmatch(t)
    if m:
        need: dict[str, int] = {}
        for sym in re.findall(r"\{(\w)\}", m["syms"]):
            need[sym] = need.get(sym, 0) + 1
        return {"object": _cast_who(m["who"]), "cast": {"spent": need}}
    for rx, key in ((_SPENT_COLOR, "spent"), (_SPENT_SAME, "same_color"), (_SPENT_TOTAL, "total")):
        m = rx.fullmatch(t)
        n = _num(m["n"]) if m else None
        if m and n:
            value: Any = {_COLOR_LETTER[m["color"]]: n} if key == "spent" else n
            return {"object": _cast_who(m["who"]), "cast": {key: value}}
    return None


def cast_conditions_on_source(cond: Condition) -> bool:
    """Is every condition about how a spell was cast in ``cond`` about the source itself (the spell, or the
    permanent it became)? (Not another object's: its record isn't kept once it resolved.)"""
    if "cast" in cond:  # (wave 5G: "no mana was spent to cast it" of a cast trigger's spell, still on the stack)
        return cond.get("object") == "self" or (cond.get("object") == "event" and bool(cond["cast"].get("no_mana")))
    return all(cast_conditions_on_source(c) for k in ("all", "any") for c in cond.get(k, ())) and (
        "not" not in cond or cast_conditions_on_source(cond["not"]))


def is_cast_condition(cond: Condition) -> bool:
    """Is (a part of) ``cond`` about how a spell was cast?"""
    return "cast" in cond or any(is_cast_condition(c) for k in ("all", "any") for c in cond.get(k, ())) or (
        "not" in cond and is_cast_condition(cond["not"]))


def _cast_holds(plan: Plan, ctx: dict[str, Any], cond: Condition) -> bool:
    """How the source was cast, from its payment record: a fact that never changes, so it is read the same while
    the spell is on the stack, once it became a permanent and after that left (608.2h). No record — it wasn't cast
    (put onto the battlefield, a copy) — fails every such test."""
    how = cond["cast"]
    if cond.get("object") == "event" and how.get("no_mana"):  # -- if you do (wave 5G) --
        return _no_mana_spent(plan, ctx)
    if cond.get("object") != "self":
        return False
    record = plan.rules.payments.get(ctx.get("source_object") or "")
    if record is None or record.cast_from is None:
        return False
    if how.get("by_you") and record.controller != ctx["controller"]:
        return False
    if how.get("kicked") and not record.kicked:  # 702.33d (a modal header's "If it was kicked, choose both instead")
        return False
    zone = how.get("from")
    if zone is not None and (record.cast_from == zone[1:] if zone.startswith("!") else record.cast_from != zone):
        return False
    if how.get("main") and not record.cast_main:
        return False
    if any(k in how for k in ("spent", "same_color", "total")) and not record.mana_known:
        return False  # (cast by hand: what paid for it isn't known — such a condition never holds)
    spent = record.mana_spent
    if any(spent.get(sym, 0) < n for sym, n in (how.get("spent") or {}).items()):
        return False
    if "same_color" in how and not any(spent.get(c, 0) >= how["same_color"] for c in "WUBRG"):
        return False
    return "total" not in how or sum(spent.values()) >= how["total"]
# -- end refused modal/conditional (wave 3R1) --


# -- if you do (wave 5G) --
def _no_mana_spent(plan: Plan, ctx: dict[str, Any]) -> bool:
    """"Whenever a player casts a spell, if no mana was spent to cast it, counter that spell." (Boromir, Vexing
    Bauble): the cast spell's payment record (601.2h: the mana that paid its total cost — convoke, delve and costs
    other than mana aren't mana). Read while the spell is on the stack (603.4: as the ability triggers and as it
    resolves); once it has left, its record is the permanent's and the counter has nothing to do anyway. A spell
    cast by hand has no known payment: the condition doesn't hold (said in the log)."""
    from app.rules import context

    refs = context._object_refs(ctx, context.EVENT)
    record = plan.rules.payments.get(refs[0].object_id) if refs else None
    if record is None or record.cast_from is None:
        return False
    if not record.mana_known:
        name = plan.state.cards[record.card].name if record.card in plan.state.cards else ""
        plan.note(f"{name or 'That spell'} was cast by hand: whether mana was spent to cast it isn't known — "
                  "apply the ability by hand", [record.card] if record.card in plan.state.cards else ())
        return False
    return sum(record.mana_spent.values()) == 0

