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


def _cmp(word: str | None) -> str:
    return "<=" if word in ("less", "fewer") else ">="


def _parse_one(t: str, objects: bool) -> Condition | None:
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
    m = _GRAVEYARD.fullmatch(t) or _GRAVEYARD_ARE.fullmatch(t)
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
                 "you don't have the initiative": "not_initiative"}


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
    if "object" in cond:
        return _object_holds(plan, ctx, cond)
    if "versus" in cond:
        return _versus(plan, ctx, cond["versus"])
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
    if got is None:
        return False
    card, ch = got
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
