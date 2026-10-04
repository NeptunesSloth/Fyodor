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

from app.rules import extremes, selectors, values

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
    if found is None:
        found = _as_cond(t) if objects else None  # -- intervening ifs (wave 11F) -- (an ability's own event: not statics)
    if found is not None:
        return found
    return _compound(t, objects)


def _compound(t: str, objects: bool) -> Condition | None:
    """"X and Y" / "X or Y" where each side is a condition by itself ("you control a Desert or there
    is a Desert card in your graveyard"), and "you control an artifact and an enchantment" (one
    subject for both). An "and" inside a noun phrase that doesn't split into conditions stays whole."""
    m = re.fullmatch(r"you control (?P<a>(?:a|an|another) .+?) (?P<j>and|or) (?P<b>(?:a|an) .+)", t)
    if m:
        parts = [_parse_one(f"you control {m[k]}", objects) for k in ("a", "b")]
        if all(p is not None for p in parts):
            return {"all" if m["j"] == "and" else "any": parts}
    m = re.fullmatch(r"(?P<a>(?:a|an) .+?) and (?P<b>(?:a|an) .+?) are in your graveyard", t)  # (wave 16F)
    if m:
        parts = [_parse_one(f"{m[k]} is in your graveyard", objects) for k in ("a", "b")]
        if all(p is not None for p in parts):
            return {"all": parts}
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
# -- token & pump wordings (wave 6C) -- "if you control seven or more lands with different names" (Field of the Dead)
_DIFFERENT_NAMES = re.compile(r"you control (?P<n>\w+) or more (?P<what>lands|creatures|artifacts|permanents) with different names")
_TOTAL_POWER = re.compile(r"creatures you control have total power (?P<n>\w+) or greater")
_GRAVEYARD = re.compile(r"there(?:'s| is| are) (?:(?P<a>a|an)|(?P<no>no)|(?P<n>\w+) or more) (?P<sel>.+? in your (?:graveyard|library))")
# (wave 16F: "a Warrior card is in your graveyard", "there are no cards in your library")
_GRAVEYARD_ARE = re.compile(r"(?:(?P<a>an?)|(?P<n>\w+) or more) (?P<sel>.+?) (?:are|is) in your graveyard")  # "seven or more cards are in your graveyard"
_ALL_GRAVEYARDS = re.compile(r"there are (?P<n>\w+) or more (?P<sel>.+?) (?:total )?in all graveyards")  # (wave 16F: Avatar of Woe)
_GRAVEYARD_TYPES = re.compile(r"there are (?P<n>\w+) or more card types among cards in your graveyard")
_NONE_ON_BATTLEFIELD = re.compile(r"(?:there are )?no (?P<sel>[\w' -]+?)(?: are)? on the battlefield")
_OBJECT_STAT = re.compile(r"(?P<who>its|that creature's|that permanent's|that card's|~'s) (?P<stat>power|toughness|mana value) "
                          r"(?:is|was) (?P<n>\w+) or (?P<cmp>less|greater|more|fewer)")
_X_IS = re.compile(r"x is (?P<n>\w+)(?: or (?P<cmp>more|greater|less|fewer))?", re.IGNORECASE)
_VERSUS = re.compile(r"an opponent (?:(?P<controls>controls)|has) more (?P<what>.+?) than you")
# -- intervening ifs (wave 11F) -- 603.4: the player the trigger event names ("that player"), the player a creature
# attacked ("defending player", 508.5) or any player ("a player"): "that player controls more lands than you",
# "you control more creatures than an opponent" (the same quantity, read for each of them)
_AS = {"that player": "event", "defending player": "defended", "a player": "any"}
_VERSUS_WHO = re.compile(r"(?P<who>that player|defending player) (?:(?P<controls>controls)|has) more (?P<what>.+?) than you")
_VERSUS_REV = re.compile(r"you (?:(?P<controls>control)|have) more (?P<what>.+?) than an opponent")
_COMMANDER = re.compile(r"you control (?P<which>your commander|a commander)")
# "it's a land card", "that creature is a Human", "~ is an enchantment", "it was a creature card"
_OBJECT_WORDS = {"it": "it", "~": "self", "that creature": "it", "that permanent": "it", "that card": "it",
                 "that land": "it", "that token": "it", "that artifact": "it"}
_OBJECT = re.compile(r"(?P<who>it|~|that (?:creature|permanent|card|land|token|artifact)) "
                     r"(?P<verb>is not|was not|isn't|wasn't|is|was) (?P<what>.+)")  # (wave 11F: "is not" before "is")
# -- intervening ifs (wave 11F) -- "~ is enchanted", "it's enchanted or equipped" (303.4, 301.5: an Aura / Equipment
# attached to it), "~ is monstrous" (701.37b), "it's renowned" (702.112b)
_ATTACHED = {"enchanted": ("Aura",), "equipped": ("Equipment",), "enchanted or equipped": ("Aura", "Equipment")}
_BEATS_SELF = re.compile(r"(?P<who>it|that creature) has greater (?P<a>power|toughness)(?: or (?P<b>power|toughness))? than ~|"
                         r"(?P<who2>its|that creature's) power is greater than ~'s(?: power)?"
                         r"(?: (?:or|and/or) (?:its|that creature's) toughness is greater than ~'s toughness)?")  # (and/or: 702.100a, wave 15E)
_STATES = {"tapped": "tapped", "untapped": "untapped", "attacking": "attacking", "blocking": "blocking",
           "suspected": "suspected", "prepared": "prepared"}  # (prepared: wave 13C, 722.3; suspected: wave 12A, 701.60 — a designation of the source, like its other states)
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


# -- counters (wave 7C) -- "~ has twenty or more growth counters on it", "there are three or more brick counters on this
# artifact", "~ has no charge counters on it": how many counters of a kind its source has now (122.1)
_SELF_COUNTS = re.compile(r"(?:(?:~|this [a-z]+) has|there (?:are|is)) (?:(?P<n>\w+) or (?P<cmp>more|fewer)|(?P<no>no)) "
                          r"(?P<k>\+1/\+1|-1/-1|[a-z]+) counters? on (?:it|~|this [a-z]+)")


def _parse_one(t: str, objects: bool) -> Condition | None:
    found_extreme = extremes.parse(t)  # -- extremes (wave 8B) -- "you control the creature with the greatest power or tied …"
    if found_extreme is not None:
        return found_extreme
    m = _SELF_COUNTS.fullmatch(t)
    if m and m["k"] not in ("any", "more", "fewer"):
        n = 0 if m["no"] else _num(m["n"])
        if n is not None:
            return {"value": {"counters": m["k"], "on": "self"}, "op": "==" if m["no"] else _cmp(m["cmp"]), "n": n}
    from app.rules import (
        coin_flips,  # -- coin flips (wave 7E) -- "If you win the flip" (705.2: app/rules/coin_flips.py)
    )

    if (flip := coin_flips.condition(t)) is not None:
        return flip
    from app.rules import dice  # -- rolling dice (wave 12A) -- "If the result is 3 or less"

    if (rolled := dice.condition(t)) is not None:
        return rolled
    # -- combat (wave 5C) -- "it's the first combat phase of the turn" (500.8: additional ones may follow), "it's your
    # main phase" (505.1)
    if t in ("it's the first combat phase of the turn", "it is the first combat phase of the turn"):
        return {"combat_phase": "first"}
    if t in ("it's your main phase", "it is your main phase"):
        return {"main_phase": "yours"}
    # "you control a Forest", "you control two or more Islands", "you control another Elf",
    # "you control no creatures", "you don't control a …", "an opponent controls a …"
    # -- as long as (wave 9B) -- "If excess damage was dealt (to that creature) this way, …" (120.10: scripts bind it to the damage
    # instruction just before, this_way.excess_dealt)
    if re.fullmatch(r"excess damage was dealt (?:to (?:that|a) (?:creature|permanent) )?this way", t):
        return {"value": {"ref_amount": "excess_dealt"}, "op": ">=", "n": 1}
    m = _DIFFERENT_POWERS.fullmatch(t)
    if m:  # "you control three or more creatures with different powers"
        n = _num(m["n"])
        key = _count("creatures", "you control")
        if n is None or key is None:
            return None
        return {"value": {"distinct": "powers", "among": key}, "op": ">=", "n": n}
    m = _DIFFERENT_NAMES.fullmatch(t)  # -- token & pump wordings (wave 6C) --
    if m:  # how many different names among them (201.2; a face-down permanent has none, 708.2a)
        n = _num(m["n"])
        key = _count(m["what"], "you control")
        if n is None or key is None:
            return None
        return {"value": {"distinct": "names", "among": key}, "op": ">=", "n": n}
    m = _COMMANDER.fullmatch(t)
    if m:  # "you control your commander" (Lieutenant): a commander you own (903.3), on the battlefield under your control
        commanders = selectors.Selector(commander=True, controller="you", owner="you" if m["which"] == "your commander" else None)
        return {"value": {"count": commanders.key()}, "op": ">=", "n": 1}
    m = re.fullmatch(r"an opponent controls at least (?P<n>\w+) more (?P<what>.+) than you", t)
    if m and _num(m["n"]) is not None:  # -- cost alt (wave 16F) -- Avatar of Might: some opponent's count is at least n above yours
        key = _count(m["what"], "you control")
        if key:
            return {"versus": {"value": {"count": key}, "op": ">=", "margin": _num(m["n"])}}
        return None
    m = re.fullmatch(r"no opponent controls (?:an? )?(?P<sel>.+)", t)  # -- as long as (wave 16F) -- none of them has one, not one opponent
    if m:
        key = _count(m["sel"], "an opponent controls")
        return {"value": {"count": key}, "op": "==", "n": 0} if key else None
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
    # -- damage wordings (wave 6B) -- "if that player has two or fewer cards in hand" (Lavaborn Muse): the hand of the
    # player "that player" names (scripts._that_players_hand binds it: the target player, or the trigger's)
    m = re.fullmatch(r"that player has (?P<n>\w+) or (?P<cmp>more|fewer|less) cards in (?:their )?hand", t)
    if m:
        n_cards = _num(m["n"])
        if n_cards is None:
            return None
        return {"value": {"hand": "that_player"}, "op": ">=" if m["cmp"] == "more" else "<=", "n": n_cards}
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
    m = _ALL_GRAVEYARDS.fullmatch(t)
    if m:  # "there are ten or more creature cards total in all graveyards": every graveyard's (400.1)
        n = _num(m["n"])
        everywhere = selectors.parse(m["sel"] + " in graveyards")
        if n is None or everywhere is None or everywhere.player is not None or everywhere.zones != ("graveyard",) \
                or everywhere.zone_owner is not None:
            return None
        return {"value": {"count": everywhere.key()}, "op": ">=", "n": n}
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
        gd = m.groupdict()
        n = 1 if gd.get("a") else 0 if gd.get("no") else _num(m["n"] or "")
        zone = "library" if m["sel"].endswith("in your library") else "graveyard"
        in_graveyard = selectors.parse(m["sel"] if f"in your {zone}" in m["sel"] else m["sel"] + f" in your {zone}")
        if n is None or in_graveyard is None or in_graveyard.player is not None or in_graveyard.zones != (zone,):
            return None
        return {"value": {"count": in_graveyard.key()}, "op": "==" if gd.get("no") else ">=", "n": n}
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
    if m is None:  # -- intervening ifs (wave 11F) -- "that player controls more lands than you", "you have more life than an opponent"
        m = (_VERSUS_WHO.fullmatch(t) if objects else None) or _VERSUS_REV.fullmatch(t)
    if m:  # "an opponent controls more lands than you" / "has more life than you"
        what = m["what"]
        quantity: Any
        if m["controls"]:
            key = _count(what, "you control")
            quantity = {"count": key} if key else None
        else:
            quantity = {"life": "you"} if what == "life" else {"hand": "you"} if what == "cards in hand" else None
        if quantity is None:
            return None
        gd = m.groupdict()
        if gd.get("who"):
            return {"versus": {"value": quantity, "op": ">", "who": _AS[gd["who"]]}}
        return {"versus": {"value": quantity, "op": "<" if m.re is _VERSUS_REV else ">"}}
    found = designation_condition(t)  # -- counters & designations (wave 3E) --
    if found is not None:
        return found
    found = _more_ifs(t)  # -- intervening ifs (wave 11F) --
    if found is not None:
        return found
    m = re.fullmatch(r"an opponent (?:(?P<has>has)|controls) (?P<rest>(?:no|\w+ or (?:more|fewer|less)) .+)", t)  # (wave 16F)
    if m:  # "an opponent has no cards in hand": the same test read for some one opponent ("you" of it is them)
        inner = _parse_one(f"you {'have' if m['has'] else 'control'} {m['rest']}", objects)
        if inner is not None and "value" in inner and not inner.get("per_opponent"):
            return {"as": "opponent", "cond": inner}
    if objects:
        found = _cast_how(t)  # -- refused modal/conditional (wave 3R1) --
        if found is not None:
            return found
        return _object(t)
    return None


# -- intervening ifs (wave 11F) -- 603.4, researched against CR 2026-09-25 ------------------------------------------------
_WHO = re.compile(r"(?P<who>that player|defending player|a player) (?P<verb>has|controls|cast) (?P<rest>.+)")
_VERBS = {"has": "have", "controls": "control", "cast": "cast"}
_MOST = re.compile(r"(?P<who>a player|that player) (?:(?P<controls>controls)|has) more (?P<what>.+?) than each other player")


def _as_cond(t: str) -> Condition | None:
    """"that player controls a Plains", "defending player has no cards in hand", "a player has one or fewer cards in
    hand": the same condition as for "you", read for the player the trigger event names, the one attacked, or some player.
    A comparison ("than") is read by the versus forms; whether the ability's event names the player is checked where it
    is defined (scripts._event_refs_ok)."""
    most = _MOST.fullmatch(t)  # "a player has more life than each other player": every other player has less
    if most:
        what = most["what"]
        if most["controls"]:
            key = _count(what, "you control")
            quantity: Any = {"count": key} if key else None
        else:
            quantity = {"life": "you"} if what == "life" else {"hand": "you"} if what == "cards in hand" else None
        if quantity is None:
            return None
        return {"as": _AS[most["who"]], "cond": {"versus": {"value": quantity, "op": "<", "every": True}}}
    m = _WHO.fullmatch(t)
    if m is None or " than " in m["rest"]:
        return None
    inner = parse(f"you {_VERBS[m['verb']]} {m['rest']}", objects=True)
    return {"as": _AS[m["who"]], "cond": inner} if inner is not None else None


_HAND_N = re.compile(r"you have (?:(?P<a>a)|exactly (?P<e>\w+)|fewer than (?P<f>\w+)|more than (?P<m>\w+)|at least (?P<l>\w+)) "
                     r"cards? in (?:your )?hand")
_BATTLEFIELD_N = re.compile(r"there (?:are|is) (?:(?P<n>\w+) or more|fewer than (?P<f>\w+)|exactly (?P<e>\w+)) (?P<sel>.+?) on the battlefield")
_GRAVEYARD_FEWER = re.compile(r"there are fewer than (?P<f>\w+) (?P<sel>.+? in your graveyard)")
_SELF_FEWER = re.compile(r"(?:~|this [a-z]+) has fewer than (?P<f>\w+) (?P<k>\+1/\+1|-1/-1|[a-z]+) counters? on (?:it|~|this [a-z]+)")
_TOTAL_STAT = re.compile(r"creatures you control have total (?P<stat>toughness) (?P<n>\w+) or greater")
_DEVOTION = re.compile(r"your devotion to (?P<a>white|blue|black|red|green)(?: and (?P<b>white|blue|black|red|green))? "
                       r"is (?P<n>\w+) or greater")
_COLORS_AMONG = re.compile(r"there are (?P<n>\w+) colors among permanents you control")
_EXACT_LIFE = re.compile(r"you have exactly (?P<n>\w+) life")
_OPPONENTS_NONE = re.compile(r"your opponents control no (?P<sel>.+)")
_CTRL_EXACT = re.compile(r"you control exactly (?P<n>\w+) (?P<sel>.+)")
_COLOR_SYMBOL = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}


def _more_ifs(t: str) -> Condition | None:
    """Hand sizes ("you have exactly thirteen cards in your hand", "a card in hand"), "there are four or more creatures
    on the battlefield", "fewer than" for counters and cards, "you control exactly one creature", total toughness,
    devotion, five colors, an exact life total."""
    m = _OPPONENTS_NONE.fullmatch(t)
    if m:  # none of them together: no opponent controls one
        key = _count(m["sel"], "an opponent controls")
        return {"value": {"count": key}, "op": "==", "n": 0} if key else None
    m = _HAND_N.fullmatch(t)
    if m:
        n = 1 if m["a"] else _num(next(g for g in (m["e"], m["f"], m["m"], m["l"]) if g))
        if n is None:
            return None
        op, n = (">=", n) if (m["a"] or m["l"]) else ("==", n) if m["e"] else ("<=", n - 1) if m["f"] else (">=", n + 1)
        return {"value": {"hand": "you"}, "op": op, "n": n}
    m = _BATTLEFIELD_N.fullmatch(t)
    if m:  # whoever controls them: the battlefield as a whole
        sel = selectors.parse(m["sel"])
        n = _num(m["n"] or m["f"] or m["e"])
        if sel is None or sel.player is not None or sel.zones != ("battlefield",) or sel.controller is not None or n is None:
            return None
        return {"value": {"count": sel.key()}, "op": ">=" if m["n"] else "==" if m["e"] else "<=", "n": n - 1 if m["f"] else n}
    m = _GRAVEYARD_FEWER.fullmatch(t)
    if m:
        sel, n = selectors.parse(m["sel"]), _num(m["f"])
        if sel is None or n is None or sel.player is not None or sel.zones != ("graveyard",):
            return None
        return {"value": {"count": sel.key()}, "op": "<=", "n": n - 1}
    m = _SELF_FEWER.fullmatch(t)
    if m and (n := _num(m["f"])) is not None and m["k"] not in ("any", "more", "fewer"):
        return {"value": {"counters": m["k"], "on": "self"}, "op": "<=", "n": n - 1}
    m = _TOTAL_STAT.fullmatch(t)
    key = _count("creatures", "you control")
    if m and _num(m["n"]) is not None and key is not None:
        return {"value": {"sum": m["stat"], "of": key}, "op": ">=", "n": _num(m["n"])}
    m = _DEVOTION.fullmatch(t)  # 700.5
    if m and _num(m["n"]) is not None:
        return {"value": {"devotion": [_COLOR_SYMBOL[c] for c in (m["a"], m["b"]) if c]}, "op": ">=", "n": _num(m["n"])}
    m = _COLORS_AMONG.fullmatch(t)  # 105.1: "there are five colors among permanents you control"
    key = _count("permanents", "you control")
    if m and _num(m["n"]) is not None and key is not None:
        return {"value": {"distinct": "colors", "among": key}, "op": ">=", "n": _num(m["n"])}
    m = _EXACT_LIFE.fullmatch(t)
    if m and _num(m["n"]) is not None:
        return {"value": {"life": "you"}, "op": "==", "n": _num(m["n"])}
    m = _CTRL_EXACT.fullmatch(t)
    if m and _num(m["n"]) is not None:
        key = _count(m["sel"], "you control")
        return {"value": {"count": key}, "op": "==", "n": _num(m["n"])} if key else None
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


# -- this-turn conditions (wave 8D) -- "if you didn't lose life this turn" (Luminarch Ascension): none was lost (119.3)
@_history_pattern(r"you(?: haven't| didn't|'ve not| have not| did not) (?P<k>lose|lost|gain|gained) life this turn")
def _no_life_change(m: re.Match[str]) -> Condition:
    gained = m["k"].startswith("gain")
    return {"not": {"history": "gained", "n": 1} if gained else {"history": "lost", "who": "you", "n": 1, **_when(m)}}


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
    m = _BEATS_SELF.fullmatch(t)  # -- intervening ifs (wave 11F) -- "if that creature has greater power or toughness than ~"
    if m:
        stats = [x for x in (m["a"], m["b"]) if x] if m["a"] else ["power"] + (["toughness"] if "toughness" in t else [])
        return {"object": "it", "beats_self": stats}
    t = re.sub(r"^(it|that (?:creature|permanent|card|land|token|artifact))'s ", r"\1 is ", t)
    t = re.sub(r"^that's (?=another )", "that creature is ", t)  # -- keywords (wave 15E) -- backup 702.165a: "If that's another creature"
    m = _OBJECT.fullmatch(t)
    if m is None:
        return None
    who = _OBJECT_WORDS[m["who"]]
    negate = m["verb"] in ("isn't", "wasn't", "is not", "was not")
    what = m["what"].strip()
    if lv := re.fullmatch(r"level (\d+)( or greater)?", what):  # -- Class (wave 16A) -- 716.2a, 716.2b
        at_level: Condition = {"object": who, "level": int(lv[1]), "min": bool(lv[2])}
        return {"not": at_level} if negate else at_level
    if what in _ATTACHED or what in ("renowned", "monstrous"):  # (wave 11F)
        test: Condition = {"object": who, **({"attached": list(_ATTACHED[what])} if what in _ATTACHED else {"designation": what})}
        return {"not": test} if negate else test
    if what in _STATES:
        if who != "self":
            return None  # (tapped / untapped / attacking / blocking: the source's own state, never an LKI guess)
        out: Condition = {"object": who, "test": _STATES[what]}
    else:
        det = re.match(r"(?:a|an|another) (?P<rest>.+)", what) if what != "another" else None
        if det is not None and what.startswith("another "):
            det = re.match(r"(?P<rest>another .+)", what)
        if det is None and re.fullmatch(r"(?:white|blue|black|red|green)(?: or (?:white|blue|black|red|green))*", what):
            det = re.match(r"(?P<rest>.+)", what + " permanent")  # "it's blue": a color test, on whatever it is
        if det is None and re.fullmatch(r"(?:non)?(?:basic|legendary|snow)", what):  # -- damage wordings (wave 6B) --
            det = re.match(r"(?P<rest>.+)", what + " permanent")  # "If that land was nonbasic": a supertype (205.4)
        sel = selectors.parse(det["rest"]) if det else None
        if (sel is None or sel.player is not None or sel.zone_owner is not None or sel.controller is not None
                or sel.owner is not None or sel.zones not in (("battlefield",), ())):
            return None  # (a test of the object's characteristics, wherever it is: no zone or player relation)
        out = {"object": who, "is": sel.key()}
    if negate:  # ("isn't": still needs the object to be there to be judged — a missing one passes no test)
        return {**out, "negate": True} if "is" in out else {"not": out}
    return out


# -- evaluation -----------------------------------------------------------------------------------------
def needs_event(cond: Condition) -> bool:
    """-- intervening ifs (wave 11F) -- does the condition read the player a trigger event names ("that player") or the one
    attacked ("defending player")? Only a triggered ability has them (scripts._event_refs_ok)."""
    if "as" in cond:
        return cond["as"] != "any" or needs_event(cond["cond"])
    return any(needs_event(c) for k in ("all", "any") for c in cond.get(k, ())) or (
        "not" in cond and needs_event(cond["not"])) or cond.get("versus", {}).get("who") in ("event", "defended")


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
    if "as" in cond:
        out += objects_in(cond["cond"])
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
    if "as" in cond:
        out["cond"] = bind_objects(cond["cond"], who)
    return out


def holds(plan: Plan, ctx: dict[str, Any], cond: Condition) -> bool:
    if "coin" in cond:  # -- coin flips (wave 7E) -- this resolution's own flip (app/rules/coin_flips.py)
        from app.rules import coin_flips

        return coin_flips.holds(ctx, cond)
    if "act7b" in cond:  # -- activation wordings (wave 7B) -- app/rules/activation_words.py
        from app.rules import activation_words

        return activation_words.holds(plan, ctx, cond)
    if "extreme" in cond:  # -- extremes (wave 8B) -- app/rules/extremes.py
        return extremes.holds(plan, ctx, cond)
    if "as" in cond:  # -- intervening ifs (wave 11F) -- a condition about another player
        return _as_holds(plan, ctx, cond)
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
    if "attacked_now" in cond:  # -- cast timing (wave 7A) -- 506.3: creatures attacking you (not your planeswalkers)
        return any(c.attacking is not None and c.attacking.kind == "player" and c.attacking.id == ctx["controller"]
                   for c in plan.state.cards.values())
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
    got = plan.state.players[ctx["controller"]].life if "life" in v and v["life"] != "player_min" \
        else values.evaluate(plan, ctx, v)  # (player_min: "a player has 13 or less life", wave 6E)
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
    the same quantity read for each of them (as "you" of that quantity). ``who`` (wave 11F): that one player instead."""
    mine = values.evaluate(plan, ctx, spec["value"])
    each = any if not spec.get("every") else all  # (wave 7A: "fewer creatures than each opponent")
    others = _as_players(plan, ctx, spec["who"]) if spec.get("who") else [p for p in plan.live() if p != ctx["controller"]]
    if spec.get("who") and len(others) != 1:
        return False
    return each(_OPS[spec["op"]](values.evaluate(plan, {**ctx, "controller": p}, spec["value"]), mine + int(spec.get("margin", 0)))
                for p in others)


def _as_players(plan: Plan, ctx: dict[str, Any], who: str) -> list[str]:
    """-- intervening ifs (wave 11F) -- the player a condition is about: the trigger event's ("that player"), the one an
    attacking creature attacked ("defending player", TriggerEvent.defended) or every player still in the game."""
    from app.rules import context

    if who == "any":
        return list(plan.live())
    if who == "opponent":  # -- cost alt (wave 16F) -- "an opponent has no cards in hand": some one opponent
        return [p for p in plan.live() if p != ctx["controller"]]
    if who == "defended":
        d = (ctx.get("event") or {}).get("defended")
        return [d] if d in plan.live() else []
    return context.players(plan, ctx, context.EVENT)


def _as_holds(plan: Plan, ctx: dict[str, Any], cond: Condition) -> bool:
    """The condition read as that player ("you" of it is them): one player, else none (a player the event doesn't name
    can't be judged); "a player": some player (603.4: also when it resolves)."""
    players = _as_players(plan, ctx, cond["as"])
    if cond["as"] not in ("any", "opponent") and len(players) != 1:
        return False
    return any(holds(plan, {**ctx, "controller": p}, cond["cond"]) for p in players)


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
    if "attached" in cond:  # -- intervening ifs (wave 11F) -- an Aura / Equipment attached to it (301.5, 303.4)
        live = plan.state.cards.get(card.id)
        if live is not None and live.zone.endswith(":battlefield"):
            ids = [c.id for c in plan.state.cards.values() if c.attached_to == card.id]
        else:  # it left: attached as it last existed (603.10a, 608.2h)
            snap = plan.rules.lki.get(ctx.get("source_object") or "") if cond["object"] == "self" else None
            snap = snap or next((x for x in reversed(plan.rules.lki.values()) if x.card == card.id), None)
            ids = list(snap.attached) if snap is not None else []
        return any(plan.ch(plan.state.cards[i]).subtypes & set(cond["attached"]) for i in ids if i in plan.state.cards)
    if "level" in cond:  # -- Class (wave 16A) -- 716.2b, 716.2d: no level is level 1
        n = plan.rules.levels.get(plan.oid(card), 1)
        return n >= cond["level"] if cond["min"] else n == cond["level"]
    if "designation" in cond:  # 701.37b, 702.112b: kept until the permanent leaves, so only the object it still is
        return plan.oid(card) in (plan.rules.monstrous if cond["designation"] == "monstrous" else plan.rules.renowned)
    if "beats_self" in cond:  # "its power is greater than ~'s": either stat named (as it is, or as it last existed, 608.2h)
        mine = values._object(plan, ctx, "self")
        if mine is None:
            return False
        pairs = [(values._stat_of(ch, st), values._stat_of(mine[1], st)) for st in cond["beats_self"]]
        return any(a is not None and b is not None and a > b for a, b in pairs)
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
        if test == "suspected":
            return plan.oid(card) in plan.rules.suspected
        if test == "prepared":  # -- prepared (wave 13C) -- 722.3a
            return plan.oid(card) in plan.rules.prepared
    else:
        snap = plan.rules.lki.get(ctx.get("source_object") or "")
        if snap is None:
            return False
        tapped, attacking, blocking = snap.tapped, snap.attacking, snap.blocking
        if test in ("suspected", "prepared"):
            return False
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
# -- ability words (wave 9C) -- opus: "If five or more mana was spent to cast that spell, …" (a cast trigger's spell)
_SPENT_TOTAL_THAT = re.compile(r"(?P<n>\w+) or more mana was spent to cast that spell")


def _cast_how(t: str) -> Condition | None:
    """A condition about how the source was cast, or None."""
    if t in ("it escaped", "~ escaped"):  # -- escape (wave 5I) -- 702.138b
        return {"object": _cast_who(t.split()[0]), "cast": {"escaped": True}}
    if _NO_MANA.fullmatch(t):  # -- if you do (wave 5G) -- "if no mana was spent to cast it" (a cast trigger's spell)
        return {"object": "it", "cast": {"no_mana": True}}
    t = re.sub(r"^at least (\w+) mana was spent", r"\1 or more mana was spent", t)  # (wave 11F: the same thing)
    if (m := _SPENT_TOTAL_THAT.fullmatch(t)) is not None and (n := _num(m["n"])):  # -- ability words (wave 9C) -- opus
        return {"object": "it", "cast": {"total": n, "event_spell": True}}
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
        return cond.get("object") == "self" or (cond.get("object") == "event" and bool(
            cond["cast"].get("no_mana") or cond["cast"].get("event_spell")))
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
    if cond.get("object") == "event" and how.get("event_spell"):  # -- ability words (wave 9C) -- opus
        return _total_mana_spent(plan, ctx, int(how["total"]))
    if cond.get("object") != "self":
        return False
    record = plan.rules.payments.get(ctx.get("source_object") or "")
    if record is None or record.cast_from is None:
        return False
    if how.get("by_you") and record.controller != ctx["controller"]:
        return False
    if how.get("kicked") and not record.kicked:  # 702.33d (a modal header's "If it was kicked, choose both instead")
        return False
    if how.get("escaped") and record.alternative != "escape":  # -- escape (wave 5I) -- 702.138b
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


# -- ability words (wave 9C) --
def _total_mana_spent(plan: Plan, ctx: dict[str, Any], need: int) -> bool:
    """Opus: "If five or more mana was spent to cast that spell, …": the total mana that paid the cast spell's cost
    (601.2h; its X counts, a cost reduction doesn't), from its payment record, read while the spell is still on the
    stack (the trigger resolves above it). If the spell is already gone, or was cast by hand (what paid for it unknown),
    the condition can't be judged: it doesn't hold and the log says to apply the ability by hand."""
    from app.rules import context

    refs = context._object_refs(ctx, context.EVENT)
    record = plan.rules.payments.get(refs[0].object_id) if refs else None
    if record is None or record.cast_from is None or not record.mana_known:
        name = plan.state.cards[record.card].name if record is not None and record.card in plan.state.cards else "That spell"
        plan.note(f"{name}: how much mana was spent to cast it isn't known — apply the ability by hand",
                  [record.card] if record is not None and record.card in plan.state.cards else ())
        return False
    return sum(record.mana_spent.values()) >= need


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

