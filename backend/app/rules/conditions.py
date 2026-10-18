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
        ">": lambda a, b: a > b, "<": lambda a, b: a < b,
        "parity": lambda a, b: a % 2 == b,  # (-- spell grants (wave 30T) -- "~'s power is even / odd" (Kianne): b 0 even, 1 odd; 0 is even, a negative odd)
        # -- counters (wave 41A) -- "you control a prime number of lands" (Zimone, All-Questioning): 2, 3, 5, 7 … (a number greater than 1 with no divisor but 1 and itself)
        "prime": lambda a, b: a > 1 and all(a % d for d in range(2, int(a ** 0.5) + 1))}


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
    t = re.sub(r"^(defending player|that player|an opponent) is poisoned$", r"\1 has a poison counter", t)  # -- player counters (wave 20F) -- 122.1f
    t = re.sub(r"^your library has no cards in it$", "there are no cards in your library", t)  # -- activated other (wave 34B) -- Doctor Doom, Unrivaled: "your library has no cards in it" is the condition "there are no cards in your library" read as the effect resolves (608.2c)
    t = re.sub(r"^you control no (\w+) other than (?:this \w+|~)(?= and |$)", r"you control no other \1", t)  # -- most-played cards (wave 49A) -- Barren Glory: "no permanents other than this enchantment"
    t = re.sub(r"^(you control no other \w+) and have ", r"\1 and you have ", t)  # (the elided subject of the second half)
    t = re.sub(r"^an? ([a-z -]+?) you control is attacking$", r"you control an attacking \1", t)  # -- cant restrictions (wave 50G) -- "As long as an artifact creature you control is attacking" (Sanwell): you control an attacking one
    t = t.replace("your team controls", "you control")  # -- trailing & intervening ifs (wave 38A) -- 102.4: outside a team game "your team" is "you" (Sickle Dancer)
    if "your starting life total" in t:  # -- trailing & intervening ifs (wave 38A) -- 119.1, 903.7: "if your life total is greater than your starting life total" (Cosmos Elixir)
        from app.rules import static_conditions

        life = static_conditions.parse(t)  # (the static grammar's reading, judged by static_conditions.life_vs_start)
        if life is not None and life.get("static") == "life_vs_start":
            return life
    # -- attached events (wave 40B) -- "enchanted creature is white and untapped" (Nature's Chosen): one subject, two adjectives
    t = re.sub(rf"^({_HOST_WORDS}) is ((?:white|blue|black|red|green|tapped|untapped|attacking|blocking)) and ((?:white|blue|black|red|green|tapped|untapped|attacking|blocking))$",
               r"\1 is \2 and \1 is \3", t)
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
_THEIR_TURN = re.compile(r"it(?:'s| is| isn't) (?P<neg>not )?(?:that player's|their) turn")  # (wave 17D: the trigger event's player, 500.1; wave 43B: "isn't", Tataru Taru)
_STATUS = {"you're the monarch": "monarch", "you are the monarch": "monarch", "you have the initiative": "initiative",
           "you or a player you're attacking has the initiative": "initiative_attack",  # -- initiative (wave 45B) -- Undercellar Sweep
           "you have the city's blessing": "city_blessing", "you have an enduring story": "enduring_story",
           "you own a card in exile": "own_exiled"}  # -- activated other (wave 21E) -- (Dreadlight Monstrosity)
_THIS_TURN = r"(?P<when>this|last) turn"
_EVENT_ATTACKING = re.compile(r"(?P<n>\w+) or more of those creatures (?:are|is) attacking you and/or planeswalkers you control")
_DIFFERENT_POWERS = re.compile(r"you control (?P<n>\w+) or more creatures with different powers")
# -- token & pump wordings (wave 6C) -- "if you control seven or more lands with different names" (Field of the Dead; wave 20D: "ten or more Gates with different names", Maze's End)
_DIFFERENT_NAMES = re.compile(r"you control (?P<n>\w+) or more (?P<what>lands|creatures|artifacts|permanents|[A-Z][a-z]+s) with different names")
_TOTAL_POWER = re.compile(r"creatures you control have total power (?P<n>\w+) or greater")
_GRAVEYARD = re.compile(r"there(?:'s| is| are) (?:(?P<a>a|an)|(?P<no>no)|(?P<n>\w+) or more) (?P<sel>.+? in your (?:graveyard|library))")
# (wave 16F: "a Warrior card is in your graveyard", "there are no cards in your library")
_GRAVEYARD_ARE = re.compile(r"(?:(?P<a>an?)|(?P<n>\w+) or more) (?P<sel>.+?) (?:are|is) in your graveyard")  # "seven or more cards are in your graveyard"
_ALL_GRAVEYARDS = re.compile(r"there are (?P<n>\w+) or more (?P<sel>.+?) (?:total )?in all graveyards")  # (wave 16F: Avatar of Woe)
_GRAVEYARD_TYPES = re.compile(r"there are (?P<n>\w+) or more (?P<what>card types|mana values) among cards in your graveyard")  # (wave 20B: mana values)
_NONE_ON_BATTLEFIELD = re.compile(r"(?:there are )?no (?P<sel>[\w' -]+?)(?: are)? on the battlefield")
_HOST_WORDS = r"(?:enchanted (?:creature|permanent|land|artifact)|equipped creature)"  # -- attached events (wave 40B) -- 301.5, 303.4: the object the source is attached to
_OBJECT_STAT = re.compile(rf"(?P<who>its|that creature's|that permanent's|that card's|the card's|that spell's|~'s|the sacrificed (?:creature|permanent|artifact)'s|{_HOST_WORDS}'s) (?P<stat>power|toughness|mana value) "
                          r"(?:is|was) (?:(?P<n>\w+) or (?P<cmp>less|greater|more|fewer)|(?P<cmp2>less|greater|more|fewer) than (?P<n2>\w+)|exactly (?P<n3>\w+))")  # (17D: "than"; 36A: "exactly 20")
_OBJECT_PARITY = re.compile(r"~'s (?P<stat>power|toughness) is (?P<p>even|odd)")
_OBJECT_VS_REVEALED = re.compile(r"(?:its|that creature's|that permanent's) (?P<stat>power|toughness|mana value) (?:is|was) (?P<cmp>less than or equal to|less than|"
                                 r"greater than or equal to|greater than|equal to) the (?P<kind>revealed|discarded) card's (?P<ref>power|toughness|mana value)")  # (wave 44D: discarded)
# -- trigger other (wave 25B) -- converge: "if its mana value is less than or equal to the number of colors of mana spent to cast this spell"
_OBJECT_VS_COLORS = re.compile(r"(?:its|that creature's|that permanent's) (?P<stat>power|toughness|mana value) (?:is|was) (?P<cmp>less than or equal to|"
                               r"equal to) the number of colors of mana spent to cast (?:this spell|~)")
# -- static_other sweep (wave 26A) -- "if its toughness is less than or equal to the number of cards in your graveyard", "if its mana value is
# less than or equal to the greatest mana value among permanents you control": the object's characteristic against a count read as it resolves
_OBJECT_VS_COUNT = re.compile(r"(?:its|that creature's|that permanent's|that card's|that spell's) (?P<stat>power|toughness|mana value) (?:is|was) (?P<cmp>less than or equal to|"
                              r"less than|greater than or equal to|greater than|equal to) (?P<v>the (?:number of|greatest|amount of unspent) .+)")  # (wave 48C: Glissa Sunseeker)
_REF_OPS = {"less than or equal to": "<=", "less than": "<", "equal to": "==", "greater than or equal to": ">=", "greater than": ">"}
_REF_STATS = {"power": "power", "toughness": "toughness", "mana value": "mana_value"}
_X_IS = re.compile(r"x is (?P<n>\w+)(?: or (?P<cmp>more|greater|less|fewer))?", re.IGNORECASE)
_VERSUS = re.compile(r"an opponent (?:(?P<controls>controls)|has) more (?P<what>.+?) than you")
# -- intervening ifs (wave 11F) -- 603.4: the player the trigger event names ("that player"), the player a creature
# attacked ("defending player", 508.5) or any player ("a player"): "that player controls more lands than you",
# "you control more creatures than an opponent" (the same quantity, read for each of them)
_AS = {"that player": "event", "defending player": "defended", "a player": "any"}
_VERSUS_WHO = re.compile(r"(?P<who>that player|defending player) (?:(?P<controls>controls)|has) more (?P<what>.+?) than you")
_NO_MORE_LIFE = re.compile(r"no opponent has more life than (?P<who>that player|defending player)")
_VERSUS_REV = re.compile(r"you (?:(?P<controls>control)|have) more (?P<what>.+?) than (?P<which>an|each) opponent")  # (wave 44A: "each opponent", Akuta)
_COMMANDER = re.compile(r"you control (?P<which>your commander|a commander)")
# -- named permanents (wave 35C) -- 201.2: "if you control creatures named Mine Worker and Power Plant Worker" (Tower Worker, Mine Worker, Power Plant
# Worker), "artifacts named Crown of Empires and Scepter of Empires" (Throne / Scepter / Crown of Empires), "a creature named Bogbrew Witch" (Festering
# Newt): a permanent with each name (the selector's ``name:`` test, 709.4a: a face-down permanent has no name, 708.2a). The plural wording names two cards,
# the singular one: "a creature named A and B" would be one card named "A and B" and is not read.
_CARD_NAME = r"[A-Z][\w'’-]*(?: (?:(?:of|the|in|on|for|to) )*[A-Z][\w'’-]*)*"  # (words that start with a capital, a small word between: no comma, no "and")
_NAMED = re.compile(rf"you (?P<neg>don't )?control (?:(?:an?) (?P<t1>creature|artifact|enchantment|land|permanent) named (?P<a1>{_CARD_NAME})"
                    rf"|(?P<t2>creature|artifact|enchantment|land|permanent)s named (?P<a2>{_CARD_NAME}) and (?P<b2>{_CARD_NAME}))")
# "it's a land card", "that creature is a Human", "~ is an enchantment", "it was a creature card"
_OBJECT_WORDS = {"it": "it", "~": "self", "enchanted creature": "host", "enchanted permanent": "host", "enchanted land": "host",
                 "enchanted artifact": "host", "equipped creature": "host", "the sacrificed creature": "cost:sacrificed", "the sacrificed permanent": "cost:sacrificed",
                 "the sacrificed artifact": "cost:sacrificed",  # (wave 16D: what a cost sacrificed, values._object)
                 "the discarded card": "cost:discarded",  # (wave 17B: the one card a cost discarded, values._object)
                  "that creature": "it", "that permanent": "it", "that card": "it", "that spell": "event",  # (33C: a cast trigger's spell, never an earlier instruction's object)
                 "that land": "it", "that token": "it", "that artifact": "it"}
_OBJECT = re.compile(rf"(?P<who>it|~|that (?:creature|permanent|card|land|token|artifact|spell)|the sacrificed (?:creature|permanent|artifact)|the discarded card|{_HOST_WORDS}) "
                     r"(?P<verb>is not|was not|isn't|wasn't|is|was) (?P<what>.+)")  # (wave 11F: "is not" before "is")
_SAME_NAME_OF = re.compile(r"it (?:doesn't|does not) have the same name as .+")  # (wave 32A)
# -- intervening ifs (wave 11F) -- "~ is enchanted", "it's enchanted or equipped" (303.4, 301.5: an Aura / Equipment
# attached to it), "~ is monstrous" (701.37b), "it's renowned" (702.112b)
_ATTACHED = {"enchanted": ("Aura",), "equipped": ("Equipment",), "enchanted or equipped": ("Aura", "Equipment")}
_BEATS_SELF = re.compile(r"(?P<who>it|that creature) has greater (?P<a>power|toughness)(?: or (?P<b>power|toughness))? than ~|"
                         r"(?P<who3>it|that creature) had power greater than ~'s(?: power)?|"  # (-- counters (wave 41A) -- Drizzt Do'Urden: as it last existed, 608.2h)
                         r"(?P<who2>its|that creature's) power is greater than ~'s(?: power)?"
                         r"(?: (?:or|and/or) (?:its|that creature's) toughness is greater than ~'s toughness)?")  # (and/or: 702.100a, wave 15E)
# -- most-played cards (wave 43B) -- "its power is greater than each other creature's power" (Selvala, Heart of the Wilds): strictly more than every other creature on the
# battlefield (anyone's), the object's as it is or as it last existed (608.2h)
_BEATS_ALL = re.compile(r"(?:its|that creature's) (?P<stat>power|toughness) is greater than each other creature's (?P=stat)")
# -- counters (wave 33C) -- "put a +1/+1 counter on that creature if its power is less than Shelinda's power": the same comparison the other way
_LESS_SELF = re.compile(r"(?:its|that creature's) power is less than ~'s(?: power)?")
# -- static_other sweep (wave 17C) -- 608.2h: "If you controlled that permanent" (Boomerang Basics): the controller it had, as it is
# or as it last existed
_CONTROLLED = re.compile(r"you (?:(?P<neg>didn't|did not|don't|do not) control|control(?:led)?) (?:it|that (?:creature|permanent|card|land|token|artifact|enchantment|planeswalker))")
_STATES = {"tapped": "tapped", "untapped": "untapped", "attacking": "attacking", "blocking": "blocking",
           "attached to a creature": "attached_to",  # (-- casting extras (wave 18E) -- reconfigure 702.151a: the source's own state)
           "suspected": "suspected", "prepared": "prepared"}  # (prepared: wave 13C, 722.3; suspected: wave 12A, 701.60 — a designation of the source, like its other states)
# -- counters (wave 5H) -- "if it had counters on it", "if it had a +1/+1 counter on it", "if ~ has counters on it",
# "if it doesn't have an indestructible counter on it": the object's counters as it is, or as it last existed
# (603.10a, 122.2: they cease to exist as it leaves)
# (-- counters sweep (wave 19D) -- "if it had no counters on it" / "had no time counters on it": the same test, negated)
_HAD_COUNTERS = re.compile(r"(?P<who>it|~|that creature|that permanent) (?:had|has|(?P<neg>doesn't have|didn't have|had no|has no)) "
                           r"(?:(?:a|an|one or more) )?(?:(?!no |any )(?P<k>\+1/\+1|-1/-1|[a-z]+) )?"
                           r"counters? on (?:it|them|~|him|her)")
# -- counter counts (wave 30L) -- "it has fewer than four +1/+1 counters on it" (Ayara's Oathsworn), "that creature has two or more
# +1/+1 counters on it" (Urdnan), "it had two or more …" (Ochre Jelly), "it has exactly four …": how many counters of a kind the object
# has (122.1), as it is, or as it last existed (608.2h; _object_holds)
_COUNT_COUNTERS = re.compile(r"(?P<who>it|~|that creature|that permanent) (?:has|had) (?:(?P<n>\w+) or (?P<cmp>more|fewer)|fewer than (?P<f>\w+)|exactly (?P<e>\w+)) "
                             r"(?P<k>\+1/\+1|-1/-1|[a-z]+) counters? on (?:it|them|~|him|her)")
# -- refused modal/conditional (wave 3R1) -- an ability the object has (a characteristic, 109.3: as it is, or as it
# last existed, 608.2h — granted ones included). Keyword abilities only; "protection" (which quality?) isn't read.
_HAS_KEYWORD = re.compile(rf"(?P<who>it|~|that (?:creature|permanent|card)|{_HOST_WORDS}) (?:has|had|(?P<neg>doesn't have|didn't have)) (?P<kw>decayed|flying|reach|haste|trample|deathtouch|"
                          r"lifelink|menace|vigilance|first strike|double strike|hexproof|indestructible|defender|infect|"
                          r"toxic|wither|flash|madness|flashback|shroud|cycling)")


def _stat_object(who: str) -> str:
    """The object a possessive names in "its power is …": the source ("~'s"), what a cost sacrificed, what the source is attached to
    ("enchanted creature's", wave 40B) or the pronoun's."""
    if who == "~'s":
        return "self"
    if who.startswith("the sacrificed"):
        return "cost:sacrificed"
    return "host" if re.fullmatch(_HOST_WORDS + "'s", who) else "it"


def _cmp(word: str | None) -> str:
    return "<=" if word in ("less", "fewer") else ">="


# -- counters (wave 7C) -- "~ has twenty or more growth counters on it", "there are three or more brick counters on this
# artifact", "~ has no charge counters on it": how many counters of a kind its source has now (122.1)
_SELF_COUNTS = re.compile(r"(?:(?:~|this [a-z]+|(?P<host>enchanted creature)) has|there (?:are|is)) (?:(?P<n>\w+) or (?P<cmp>more|fewer)|(?P<no>no)|exactly (?P<ex>\w+)) "  # (wave 30L: exactly)
                          r"(?P<k>\+1/\+1|-1/-1|[a-z]+) counters? on (?:it|~|this [a-z]+)")


def _parse_one(t: str, objects: bool) -> Condition | None:
    from app.rules import (
        merged,  # -- merged permanents (wave 18D) -- "you both own and control ~ and a creature named X" (701.42a)
    )

    if (pair := merged.condition(t)) is not None:
        return pair
    if t.lower() in ("you control a ring-bearer", "you don't control a ring-bearer"):  # (wave 25B: before the "you control a …" selector reading)
        return {"status": _DESIGNATIONS[t.lower()]}
    found_extreme = extremes.parse(t)  # -- extremes (wave 8B) -- "you control the creature with the greatest power or tied …"
    if found_extreme is not None:
        return found_extreme
    m = re.fullmatch(r"(?:~|this [a-z]+) has an (?P<p>even|odd) number of counters on (?:it|~)", t)
    if m:  # -- commander sweep (wave 49B) -- "~ has an even number of counters on it" (Sab-Sunen, Luxa Embodied): all kinds together (122.1); zero is even
        return {"value": {"counters": None, "on": "self"}, "op": "parity", "n": int(m["p"] == "odd")}
    m = re.fullmatch(r"there are (?P<n>\w+) or more counters on (?:it|~|this [a-z]+)", t)
    if m and (n := _num(m["n"])) is not None:  # -- value grammar (wave 51C) -- "there are twenty or more counters on it" (Twenty-Toed Toad): all kinds together (122.1)
        return {"value": {"counters": None, "on": "self"}, "op": ">=", "n": n}
    m = _SELF_COUNTS.fullmatch(t)
    if m and m["k"] not in ("any", "more", "fewer"):
        n = 0 if m["no"] else _num(m["ex"] or m["n"])
        if n is not None:
            # (-- attached events (wave 20A) -- "Then if enchanted creature has three or more +1/+1 counters on it": what it's attached to)
            return {"value": {"counters": m["k"], "on": "host" if m["host"] else "self"}, "op": "==" if m["no"] or m["ex"] else _cmp(m["cmp"]), "n": n}
    from app.rules import (
        coin_flips,  # -- coin flips (wave 7E) -- "If you win the flip" (705.2: app/rules/coin_flips.py)
    )

    if (flip := coin_flips.condition(t)) is not None:
        return flip
    from app.rules import voting  # -- voting (wave 18C) -- "If death gets more votes" (701.38)

    if (voted := voting.condition(t)) is not None:
        return voted
    from app.rules import dice  # -- rolling dice (wave 12A) -- "If the result is 3 or less"

    if (rolled := dice.condition(t)) is not None:
        return rolled
    # -- combat (wave 5C) -- "it's the first combat phase of the turn" (500.8: additional ones may follow), "it's your
    # main phase" (505.1)
    if t in ("it's the first combat phase of the turn", "it is the first combat phase of the turn"):
        return {"combat_phase": "first"}
    if t in ("it's your main phase", "it is your main phase"):
        return {"main_phase": "yours"}
    if t in ("it isn't your main phase", "it is not your main phase"):  # -- blight (wave 51E) -- Dose of Dawnglow: any other time, an opponent's main phase included
        return {"not": {"main_phase": "yours"}}
    if t == "it's the first combat phase of your turn":  # -- trigger other (wave 44D) -- Tifa, Martial Artist: also this player's own turn (500.1)
        return {"combat_phase": "first_yours"}
    if t == "it's combat":  # -- trigger other (wave 44D) -- 506.1: "Whenever you cast a spell during combat" (Zuko): the combat phase, any of its steps
        return {"combat_phase": "any"}
    # "you control a Forest", "you control two or more Islands", "you control another Elf",
    # "you control no creatures", "you don't control a …", "an opponent controls a …"
    # -- as long as (wave 9B) -- "If excess damage was dealt (to that creature) this way, …" (120.10: scripts bind it to the damage
    # instruction just before, this_way.excess_dealt)
    if re.fullmatch(r"excess damage was dealt (?:to (?:that|a) (?:creature|permanent) )?this way", t):
        return {"value": {"ref_amount": "excess_dealt"}, "op": ">=", "n": 1}
    if t == "no other creatures are attacking that player":  # -- commanders (wave 50C) -- Jin Sakai, Ghost of Tsushima: 603.4, the creature that attacked is the only one attacking the player it attacked
        return {"alone_on_player": True}
    m = _EVENT_ATTACKING.fullmatch(t)
    if m and (n := _num(m["n"])) is not None:  # -- trailing & intervening ifs (wave 38A) -- 508.5, 603.4 (Mangara, Tomik): read again as the ability resolves
        return {"event_attacking": n}
    m = re.fullmatch(r"the number of attacking creatures is greater than the number of (?P<k>\+1/\+1|-1/-1|[a-z]+) counters on ~", t)
    if m and (key := _count("attacking creatures", "")) is not None:  # -- counters (wave 41A) -- ED-E, Lonesome Eyebot: counted as it triggers and again as it resolves (603.4; the ruling of 2024-03-08)
        return {"value": {"count": key}, "op": ">", "n": {"counters": m["k"], "on": "self"}}
    m = re.fullmatch(r"you control a prime number of (?P<what>lands|creatures|artifacts|enchantments)", t)
    if m and (key := _count(m["what"], "you control")) is not None:  # -- counters (wave 41A) -- Zimone, All-Questioning: read as it triggers and as it resolves (603.4)
        return {"value": {"count": key}, "op": "prime", "n": 0}
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
    m = _NAMED.fullmatch(t)  # -- named permanents (wave 35C) -- one permanent with each name
    if m:
        base = selectors.parse(f"{m['t1'] or m['t2']} you control")
        if base is None:
            return None
        names = [n for n in (m["a1"], m["a2"], m["b2"]) if n]
        parts: list[Condition] = [{"value": {"count": replace(base, extras=(*base.extras, "name:" + n)).key()}, "op": ">=", "n": 1} for n in names]
        if m["neg"]:  # -- if you do (wave 44A) -- "if you don't control a creature named Darkstar" (Rufus Shinra): none with that name (one name only)
            return {"value": parts[0]["value"], "op": "==", "n": 0} if len(parts) == 1 else None
        return parts[0] if len(parts) == 1 else {"all": parts}
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
    # -- hideaway (wave 29D) -- "each player has no cards in hand" (Howltooth Hollow: every player still in the game), "a library has twenty or fewer
    # cards in it" (Shelldock Isle: some library, whoever's; the counts are public), "there are cards exiled with it" (Evercoat Ursine, 607.2a)
    if t == "each player has no cards in hand":
        return {"as": "any", "every": True, "cond": {"value": {"hand": "you"}, "op": "==", "n": 0}}
    m = re.fullmatch(r"a library has (?P<n>\w+) or (?P<cmp>more|fewer) cards in it", t)
    if m and (n_cards := _num(m["n"])) is not None:
        return {"as": "any", "cond": {"value": {"library": "you"}, "op": ">=" if m["cmp"] == "more" else "<=", "n": n_cards}}
    if t in ("there are cards exiled with it", "there are cards exiled with ~"):
        return {"value": {"exiled_with": 1}, "op": ">=", "n": 1}
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
    m = _THEIR_TURN.fullmatch(t)
    if m:  # -- triggers (wave 17D) -- "if it's not that player's turn" (Price of Glory): the player the trigger event is about
        theirs: Condition = {"turn": "event_player"}
        return {"not": theirs} if m["neg"] or t.startswith("it isn't") else theirs
    if t in _STATUS:
        return {"status": _STATUS[t]}
    if t.lower() == "you chose a creature other than ~ as your ring-bearer":  # -- triggers (wave 19B) -- 701.54a: the creature this tempt chose
        return {"ring_other": True}
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
    m = re.fullmatch(r"there are (?P<n>\w+) or more cards in exile", t)
    if m and (n := _num(m["n"])) is not None and (exiled := selectors.parse("cards in exile")) is not None:  # -- cant restrictions (wave 50G) -- "unless there are seven or
        return {"value": {"count": exiled.key()}, "op": ">=", "n": n}  # or more cards in exile" (Ketramose): every player's exile zone, 400.1
    m = re.fullmatch(r"a graveyard has (?P<n>\w+) or more cards in it", t)
    if m and (n := _num(m["n"])) is not None:  # -- value grammar (wave 51C) -- "If a graveyard has twenty or more cards in it" (Visions of Beyond): some player's graveyard (404.1)
        return {"value": {"graveyards_with": n}, "op": ">=", "n": 1}
    m = _GRAVEYARD_TYPES.fullmatch(t)
    if m:  # delirium: "there are four or more card types among cards in your graveyard" (205.2a)
        n = _num(m["n"])
        amount = values.parse_count(f"{m['what']} among cards in your graveyard")
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
    if t in ("you have the most life or are tied for most life", "you have the most life or you're tied for most life"):  # -- most-played cards IV (wave 51G) -- Preacher of the Schism: no opponent has more life than you (every other player is an opponent in Commander, 102.2)
        return {"versus": {"value": {"life": "you"}, "op": "<=", "every": True}}
    m = _NO_MORE_LIFE.fullmatch(t)  # -- if you do (wave 21C) -- "no opponent has more life than that player" (Alliance commanders)
    if m:  # 603.4: every opponent of the controller has at most that player's life (that player may be one of them)
        return {"versus": {"value": {"life": "you"}, "op": "<=", "every": True, "ref": _AS[m["who"]]}}
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
        return {"versus": {"value": quantity, "op": "<" if m.re is _VERSUS_REV else ">", **({"every": True} if gd.get("which") == "each" else {})}}
    found = designation_condition(t)  # -- counters & designations (wave 3E) --
    if found is not None:
        return found
    found = _more_ifs(t)  # -- intervening ifs (wave 11F) --
    if found is not None:
        return found
    m = re.fullmatch(r"an opponent (?:(?P<has>has)|controls) (?P<rest>(?:no|\w+ or (?:more|fewer|less)) .+ in (?:hand|their graveyard)|\d+ or (?:more|less) life)", t)  # (wave 16F; 44D: Sheoldred's graveyard; 49C: "an opponent has 10 or less life")
    if m and (objects or not m["rest"].endswith(" life")):  # "an opponent has no cards in hand": the same test read for some one opponent ("you" of it is them)
        # (wave 49C: "has 10 or less life" only inside an ability, a trigger's: a static keeps its own ``opp_life`` form)
        inner = _parse_one(f"you {'have' if m['has'] else 'control'} {m['rest'].replace('their graveyard', 'your graveyard')}", objects)
        if inner is not None and "value" in inner and not inner.get("per_opponent"):
            return {"as": "opponent", "cond": inner}
    if objects:
        found = _cast_how(t)  # -- refused modal/conditional (wave 3R1) --
        if found is not None:
            return found
        return _object(t)
    return None


# -- intervening ifs (wave 11F) -- 603.4, researched against CR 2026-09-25 ------------------------------------------------
_WHO = re.compile(r"(?P<who>that player|defending player|a player) (?P<verb>has|controls|cast|had|(?:didn't|did not|hasn't) cast) (?P<rest>.+)")
_VERBS = {"has": "have", "controls": "control", "cast": "cast", "didn't cast": "didn't cast", "did not cast": "did not cast",
          "hasn't cast": "haven't cast", "had": "had"}  # -- event-player history (wave 30U) -- "if that player didn't cast a spell this turn" (Impatience): "you didn't cast …" read as them
_WHO_STATUS = re.compile(r"(?P<who>that player|defending player) (?P<status>is the monarch|has the initiative)")
_STATUS_WORDS = {"is the monarch": "monarch", "has the initiative": "initiative"}
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
    m = _WHO_STATUS.fullmatch(t)  # -- trailing & intervening ifs (wave 38A) -- "if defending player is the monarch" (M'Baku): that player's designation, as it is now
    if m:
        return {"as": _AS[m["who"]], "cond": {"status": _STATUS_WORDS[m["status"]]}}
    m = _WHO.fullmatch(t)
    if m is None or " than " in m["rest"]:
        return None
    inner = parse(f"you {_VERBS[m['verb']]} {m['rest'].replace('under their control', 'under your control')}", objects=True)
    if inner is not None and inner.get("history") == "entered" and inner.get("other"):
        inner = {**inner, "other": "event"}  # -- this-turn state (wave 33D) -- "if that player had another land enter …": other than the one the event is about
    return {"as": _AS[m["who"]], "cond": inner} if inner is not None else None


_HAND_N = re.compile(r"you have (?:(?P<a>a)|exactly (?P<e>\w+)|fewer than (?P<f>\w+)|more than (?P<m>\w+)|at least (?P<l>\w+)) "
                     r"cards? in (?:your )?hand")
_BATTLEFIELD_N = re.compile(r"there (?:are|is) (?:(?P<n>\w+) or more|fewer than (?P<f>\w+)|exactly (?P<e>\w+)) (?P<sel>.+?) on the battlefield")
# -- static_other (wave 42A) -- "there's another creature on the battlefield" (Shauku, Endbringer), "an enchantment is on the battlefield" (Wirecat): one or more
# of them, whoever controls them (the source itself is not "another")
_BATTLEFIELD_ONE = re.compile(r"(?:there(?:'s| is) (?P<a>an?|another) (?P<s1>[\w' -]+?)|(?P<b>an?) (?P<s2>[\w' -]+?) is) on the battlefield")
_GRAVEYARD_FEWER = re.compile(r"there are fewer than (?P<f>\w+) (?P<sel>.+? in your graveyard)")
_SELF_FEWER = re.compile(r"(?:~|this [a-z]+) has fewer than (?P<f>\w+) (?P<k>\+1/\+1|-1/-1|[a-z]+) counters? on (?:it|~|this [a-z]+)")
# -- counter counts (wave 30L) -- "there are four or more lore counters among Sagas you control" (Tom Bombadil), "there are thirty or more
# counters among artifacts and creatures you control" (Lux Artillery), "… three or more different kinds of counters among creatures you
# control" (Hundred-Battle Veteran): the counters on a group of permanents, read as it is checked (122.1; values: counters_among)
_COUNTERS_AMONG_IF = re.compile(r"there (?:are|is) (?:(?P<n>\w+) or (?P<cmp>more|fewer)|exactly (?P<e>\w+)) "
                                r"(?P<what>(?:different kinds of counters|(?:(?:\+1/\+1|-1/-1|[a-z]+) )?counters) among .+)")
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
    m = _BATTLEFIELD_ONE.fullmatch(t)
    if m:  # whoever controls them: the battlefield as a whole
        sel = selectors.parse(("another " if m["a"] == "another" else "") + (m["s1"] or m["s2"]))
        if sel is None or sel.player is not None or sel.zones != ("battlefield",) or sel.controller is not None or sel.card:
            return None
        return {"value": {"count": sel.key()}, "op": ">=", "n": 1}
    m = _GRAVEYARD_FEWER.fullmatch(t)
    if m:
        sel, n = selectors.parse(m["sel"]), _num(m["f"])
        if sel is None or n is None or sel.player is not None or sel.zones != ("graveyard",):
            return None
        return {"value": {"count": sel.key()}, "op": "<=", "n": n - 1}
    m = _SELF_FEWER.fullmatch(t)
    if m and (n := _num(m["f"])) is not None and m["k"] not in ("any", "more", "fewer"):
        return {"value": {"counters": m["k"], "on": "self"}, "op": "<=", "n": n - 1}
    m = _COUNTERS_AMONG_IF.fullmatch(t)  # -- counter counts (wave 30L) --
    if m and (n := _num(m["n"] or m["e"])) is not None and (among := values.parse_count(m["what"])) is not None:
        return {"value": among, "op": "==" if m["e"] else _cmp(m["cmp"]), "n": n}
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
    m = re.fullmatch(r"there are (?P<n>\w+) basic land types among lands you control", t)  # -- trigger other (wave 44D) -- 205.3i: "five basic land types" (Nael, Avizoa Aeronaut)
    land_key = _count("lands", "you control")
    if m and _num(m["n"]) is not None and land_key is not None:
        return {"value": {"distinct": "basic_land_types", "among": land_key}, "op": ">=", "n": _num(m["n"])}
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
_COMPLETED = re.compile(r"you(?: (?P<neg>haven't|have not)|'ve| have) completed (?P<d>Lost Mine of Phandelver|Dungeon of the Mad Mage|Tomb of Annihilation|Undercity)")
_DESIGNATIONS = {"there is no monarch": "no_monarch", "an opponent is the monarch": "opponent_monarch",
                 "you're not the monarch": "not_monarch", "you aren't the monarch": "not_monarch",
                 "you don't have the initiative": "not_initiative", "you've completed a dungeon": "completed_dungeon",
                 "you have completed a dungeon": "completed_dungeon",
                 "it's day": "day", "it's night": "night", "it's neither day nor night": "neither_day_nor_night",
                 "you control a ring-bearer": "ring_bearer", "you don't control a ring-bearer": "no_ring_bearer"}  # (wave 25B: 701.54e)


# -- speed (wave 24B) -- 702.179e: "you have max speed" is speed 4 (or more: Gomif's speed can pass 4 and stays at max speed)
_SPEED = re.compile(r"you (?P<neg>don't |do not )?have max speed|your speed is (?:less than (?P<lt>\w+)|(?P<n>\w+) or (?P<cmp>greater|higher|more|less|lower))")


def _speed_condition(s: re.Match[str]) -> Condition | None:
    speed: dict[str, Any] = {"player_counters": "speed"}
    if s["lt"] or s["cmp"] in ("less", "lower"):
        n = _num(s["lt"] or s["n"])
        return None if n is None else {"value": speed, "op": "<=", "n": n - 1 if s["lt"] else n}
    if s["n"] is None:  # max speed
        return {"value": speed, "op": "<=" if s["neg"] else ">=", "n": 3 if s["neg"] else 4}
    n = _num(s["n"])
    return None if n is None else {"value": speed, "op": ">=", "n": n}


def designation_condition(t: str) -> Condition | None:
    if (s := _SPEED.fullmatch(t)) is not None:
        return _speed_condition(s)
    from app.rules import pairing  # -- soulbond (wave 24B) --

    if (p := pairing.condition(t)) is not None:
        return p
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
    if (c := _COMPLETED.fullmatch(t)) is not None:  # -- dungeons (wave 45B) -- 309.7: "if you haven't completed Tomb of Annihilation" (Acererak the Archlich)
        held: Condition = {"status": f"completed:{c['d']}"}
        return {"not": held} if c["neg"] else held
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


@_history_pattern(r"a player was dealt combat damage this turn by a source you controlled that shared a creature type with this spell")
def _prowl(m: re.Match[str]) -> Condition:
    return {"history": "prowl"}  # -- static_other sweep (wave 17C) -- prowl, 702.76a (history._prowl)


@_history_pattern(r"a player was dealt combat damage this turn by a creature that, at the time it dealt that damage, was an assassin creature or a commander "
                  r"under your control")
def _freerunning(m: re.Match[str]) -> Condition:
    return {"history": "freerunning"}  # -- cast keywords (wave 43D) -- freerunning, 702.173a (history._freerunning)


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


@_history_pattern(r"you(?:'ve)? rolled (?P<n>\w+) or more dice this turn")
def _rolled(m: re.Match[str]) -> Condition | None:
    n = _num(m["n"])
    return None if n is None else {"history": "rolled", "n": n}  # -- dice (wave 24B) -- 706.6 (history.rolled via the turn log)


@_history_pattern(r"a creature you controlled died this turn")
def _died_mine(m: re.Match[str]) -> Condition:
    return {"history": "died", "who": "you", "n": 1}


@_history_pattern(r"a permanent (?:left the battlefield under your control|you controlled left the battlefield) this turn")
def _left(m: re.Match[str]) -> Condition:
    return {"history": "left", "who": "you"}  # revolt (700.4: leaves the battlefield = moves to another zone)


@_history_pattern(r"(?:you(?:'ve)?|your team) gained (?:life|(?P<n>\w+) or more life) this turn")  # (wave 30R: 102.4, outside a team game "your team" is you)
def _gained(m: re.Match[str]) -> Condition | None:
    n = _num(m["n"]) if m["n"] else 1
    return None if n is None else {"history": "gained", "n": n}


@_history_pattern(rf"(?P<who>you(?:'ve)?|an opponent(?: has)?|a player other than you(?: has)?|a player(?: has)?) lost (?:life|(?P<n>\w+) or more life) {_THIS_TURN}")
def _lost(m: re.Match[str]) -> Condition | None:
    n = _num(m["n"]) if m["n"] else 1
    who = "you" if m["who"].startswith("you") else "opponent" if m["who"].startswith(("an opponent", "a player other")) else "any"  # (wave 30U: Ludevic)
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


@_history_pattern(r"an opponent has drawn (?P<n>\w+) or more cards this turn")
def _opponent_drew(m: re.Match[str]) -> Condition | None:
    n = _num(m["n"])  # (wave 49A) one opponent, not all of them together
    return None if n is None else {"history": "drew", "who": "opponent", "n": n}


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
    if sel is None or not history.note_selector_ok(sel, spell=zone == "stack") or sel.zones != (zone,):
        return None
    return sel.key()


@_history_pattern(r"~ (?P<neg>didn't |did not )?attack(?:ed)? this (?P<when>turn|combat)")
def _self_attacked(m: re.Match[str]) -> Condition:
    found: Condition = {"history": "self_attacked", "object": "self",  # 508.1: this object was declared as an attacker this turn
                        **({"combat": True} if m["when"] == "combat" else {})}  # (-- trailing & intervening ifs (wave 38A) -- in this combat phase: Tolsimir)
    return {"not": found} if m["neg"] else found


@_history_pattern(r"~ (?:didn't|did not) enter the battlefield this turn")
def _self_not_entered(m: re.Match[str]) -> Condition:
    return {"not": {"history": "entered_self", "object": "self"}}  # ("object": what "it" after it names, 608.2c)


@_history_pattern(r"~ dealt (?P<kind>combat )?damage to an opponent this turn")
def _self_dealt(m: re.Match[str]) -> Condition:
    return {"history": "damage", "who": "opponent", "n": 1, "by_self": True, "object": "self", **({"combat": True} if m["kind"] else {})}


@_history_pattern(r"a source you controlled dealt (?P<n>\w+) or more damage this turn")
def _source_dealt(m: re.Match[str]) -> Condition | None:
    n = _num(m["n"])  # -- this-turn state (wave 42B) -- 120.3, 608.2i: ONE source's total over every recipient and every damage event (Dragon Cultist)
    return None if n is None else {"history": "source_damage", "who": "you", "n": n}


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


@_history_pattern(r"you attacked with creatures with total power (?P<n>\w+) or greater this combat")
def _attackers_power(m: re.Match[str]) -> Condition | None:
    n = _num(m["n"])  # -- trigger other (wave 25B) -- pack tactics: the creatures declared as attackers in this combat's declaration (508.1)
    return None if n is None else {"history": "attackers_power", "n": n}


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


# -- history (wave 22E) -- werewolves: "if no spells were cast last turn" / "if a player cast two or more spells last turn" -
# the turn before this one (500.4), by anyone; the second is ONE player's own count (not the players added up).
@_history_pattern(rf"no spells were cast {_THIS_TURN}")
def _no_spells_were_cast(m: re.Match[str]) -> Condition | None:
    key = _history_sel("spell", "stack")
    return None if key is None else {"not": {"history": "cast", "who": "any", "sel": key, "n": 1, "op": ">=", **_when(m)}}


@_history_pattern(rf"a player cast (?P<n>\w+) or more spells {_THIS_TURN}")
def _a_player_cast_spells(m: re.Match[str]) -> Condition | None:
    n, key = _num(m["n"]), _history_sel("spell", "stack")
    return None if n is None or key is None else {"history": "cast", "who": "player", "sel": key, "n": n, "op": ">=", **_when(m)}


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


_COUNTER_KINDS = ("+1/+1", "-1/-1", "loyalty", "oil", "lore", "shield", "stun")


# -- long tail (wave 16D) -- "if you put a counter on a creature this turn" (the player who put them: the event's actor,
# 122.6; whoever controls the permanent), "as long as you've put one or more +1/+1 counters on a creature this turn"
@_history_pattern(r"you(?:'ve| have)? put (?:a|an|one or more) (?:(?P<k>\S+) )?counters? on (?:a|an) (?P<sel>.+?) this turn")
def _counters_by_you(m: re.Match[str]) -> Condition | None:
    key = _history_sel(m["sel"], "battlefield")
    if key is None or (m["k"] is not None and m["k"] not in _COUNTER_KINDS):
        return None
    return {"history": "facts", "kind": "counters", "who": "any", "by": "you", "sel": key, "n": 1,
            **({"counter": m["k"]} if m["k"] else {})}


@_history_pattern(r"(?:a|an|one or more) (?:(?P<k>\S+) )?counters? (?:was|were) put on ~ this turn")  # (anyone put it: "if a counter was put on ~")
def _counters_on_self(m: re.Match[str]) -> Condition | None:
    if m["k"] is not None and m["k"] not in _COUNTER_KINDS:
        return None
    return {"history": "facts", "kind": "counters", "who": "any", "self": True, "n": 1, **({"counter": m["k"]} if m["k"] else {})}


@_history_pattern(r"you(?:'ve| have)? committed a crime this turn")
def _crime(m: re.Match[str]) -> Condition:
    return {"history": "facts", "kind": "crime", "who": "you", "n": 1}  # 700.13


@_history_pattern(r"this is the (?P<nth>first|second|third|fourth|fifth) time this ability has resolved this turn")
def _resolution(m: re.Match[str]) -> Condition:
    return {"history": "resolution", "n": ["first", "second", "third", "fourth", "fifth"].index(m["nth"]) + 1}


@_history_pattern(r"this ability has been activated (?P<n>\w+) or more times this turn")
def _activations(m: re.Match[str]) -> Condition | None:
    n = _num(m["n"])  # -- activations (wave 19E) -- Dragon Whelp: counted as each is activated (ability_uses), read as it resolves
    return None if n is None else {"history": "activations", "n": n}


@_history_pattern(r"a spell was warped this turn")
def _warped(m: re.Match[str]) -> Condition:
    return {"history": "warped"}  # -- void (wave 19E) -- 702.185a: cast for its warp cost


@_history_pattern(r"you(?:'ve| have)? played a land this turn")
def _played_land(m: re.Match[str]) -> Condition:
    return {"history": "lands", "n": 1}  # 305.1 / 701.18a: played, not put onto the battlefield


@_history_pattern(r"you(?: didn't| did not| haven't| have not) play(?:ed)? a land this turn")
def _no_land(m: re.Match[str]) -> Condition:
    return {"not": {"history": "lands", "n": 1}}


@_history_pattern(r"you had (?P<q>a|an|another|\w+ or more) (?P<sel>.+?) enter the battlefield under your control this turn")
def _had_enter(m: re.Match[str]) -> Condition | None:
    return _entered(m)


@_history_pattern(r"you had (?P<q>a|an|another|\w+ or more) (?P<sel>.+?) enter the battlefield under your control last turn")
def _had_enter_last(m: re.Match[str]) -> Condition | None:
    found = _entered(m)  # -- trailing & intervening ifs (wave 38A) -- 608.2i: the turn before this one (Ephara, God of the Polis)
    return None if found is None else {**found, "last": True}


@_history_pattern(r"(?P<q>a|an|another|\w+ or more) (?P<sel>.+?) entered the battlefield under an opponent's control this turn")
def _entered_opponent(m: re.Match[str]) -> Condition | None:
    found = _entered(m)
    return None if found is None or found.get("other") else {**found, "who": "opponent"}


# (-- this-turn history (wave 30R) -- "a nontoken creature you controlled died", "a creature an opponent controlled died", "a permanent was put
# into your hand from the battlefield" (Barrin): who controlled it as it left, and the zone it went to, both recorded as it left (Departure))
@_history_pattern(rf"{_Q} (?P<sel>.+?)(?P<nn> not named ~)?(?P<ctl> you controlled| an opponent controlled)? "
                  r"(?P<verb>died|left the battlefield|(?:was|were) put into (?P<gy>a|your) (?P<dest>graveyard|hand) from the battlefield)"
                  r"(?P<whose> under your control| under an opponent's control)? this turn")
def _departed(m: re.Match[str]) -> Condition | None:
    q = _q(m["q"])
    sel = m["sel"]
    key = _history_sel(sel, "battlefield")
    if q is None or key is None or (m["ctl"] and m["whose"]):
        return None
    out: Condition = {"history": "departed", "sel": key, "n": q[0], "op": q[1],
                      "died": not m["verb"].startswith("left") and m["dest"] != "hand"}  # 700.4: dies = put into a graveyard from the battlefield
    if m["nn"]:
        out["not_named"] = True  # -- this-turn state (wave 42B) -- "a creature not named ~ died this turn" (Ebondeath): its name as it last existed (201.2, 608.2i)
    if m["dest"] == "hand":
        out["to"] = "hand"  # (400.3: a permanent goes to its owner's hand — "your hand" is read as its owner's)
        if m["gy"] != "your":
            return None
    if side := m["whose"] or m["ctl"]:
        out["who"] = "opponent" if "opponent" in side else "you"
    if m["q"] == "another":
        out["other"] = True
    if m["gy"] == "your":
        out["owner"] = "you"  # (a permanent goes to its owner's graveyard, 400.3)
    return out


# -- this-turn state (wave 33D) -- what happened to or by ONE object, or to a player, this turn (TurnLog, 608.2i; app/rules/history.py reads
# it by the object's rules object id, so a creature that has died is still found, 400.7 / 603.10a). "it" / "that creature" are bound
# like any pronoun in a condition (bind_objects); "~" is the source.
_HO = r"(?P<o>~|it|that (?:creature|permanent|token))"


def _obj(m: re.Match[str], what: str, **kw: Any) -> Condition:
    return {"history": "object", "object": _OBJECT_WORDS[m["o"]], "what": what, **kw}


def _damage_kind(m: re.Match[str]) -> dict[str, Any]:
    return {"combat": m["kind"].strip() == "combat"} if m["kind"] else {}  # 120.2: combat or noncombat damage


@_history_pattern(rf"{_HO} (?P<neg>wasn't|was not|was) dealt (?:(?P<n>\w+) or more )?(?P<kind>combat |noncombat )?damage this turn")
def _object_dealt(m: re.Match[str]) -> Condition | None:
    n = _num(m["n"]) if m["n"] else 1  # (the damage dealt, after prevention: 120.3; a creature that left and came back is a new object)
    if n is None:
        return None
    return _obj(m, "damaged", n=n, **_damage_kind(m), **({"negate": True} if m["neg"] != "was" else {}))


# -- trigger damage (wave 39B) -- 120.10: "if that creature was dealt excess damage this turn" (Maarika), "if a creature or planeswalker an opponent
# controlled was dealt excess damage this turn" (Rith): the turn's log keeps the excess each damage event dealt to a permanent (TurnFact.excess)
@_history_pattern(rf"{_HO} (?P<neg>wasn't|was not|was) dealt excess damage this turn")
def _object_dealt_excess(m: re.Match[str]) -> Condition:
    return _obj(m, "damaged", n=1, excess=True, **({"negate": True} if m["neg"] != "was" else {}))


@_history_pattern(r"an? (?P<sel>.+?) (?P<ctl>you|an opponent) controlled (?:was|were) dealt excess damage this turn")
def _any_dealt_excess(m: re.Match[str]) -> Condition | None:
    key = _history_sel(m["sel"], "battlefield")  # (the types it was as it was dealt the damage: 608.2i)
    return None if key is None else {"history": "facts", "kind": "damaged", "excess": True, "sel": key, "n": 1,
                                     "who": "you" if m["ctl"] == "you" else "opponent"}


@_history_pattern(rf"an? (?P<kinds>[A-Z]\w+(?:(?:, or | or |, )[A-Za-z]\w+)*) you controlled dealt damage to {_HO} this turn")
def _dealt_by_kinds(m: re.Match[str]) -> Condition | None:
    """"if a Giant, Wizard, or spell you controlled dealt damage to it this turn" (Aegar): a source of one of those creature types or a spell,
    under your control as it dealt the damage (the log keeps the source's types and controller as they were then, 608.2i)."""
    from app.rules.creature_types import CREATURE_TYPES

    kinds = re.split(r", or |, | or ", m["kinds"])
    spell = "spell" in kinds
    types = [k for k in kinds if k != "spell"]
    if not types or not all(t in CREATURE_TYPES for t in types):
        return None
    return _obj(m, "damaged_by", subtypes=types, spell=spell)


@_history_pattern(rf"(?P<n>\w+) or more (?P<kind>combat |noncombat )?damage was dealt to {_HO} this turn")
def _damage_dealt_to_object(m: re.Match[str]) -> Condition | None:
    n = _num(m["n"])
    return None if n is None else _obj(m, "damaged", n=n, **_damage_kind(m))


@_history_pattern(rf"{_HO} (?P<neg>wasn't|was not|was) blocked this turn")
def _object_blocked(m: re.Match[str]) -> Condition:
    return _obj(m, "blocked", **({"negate": True} if m["neg"] != "was" else {}))  # 509.1g: declared as blocked by a blocker


@_history_pattern(rf"{_HO} attacked or blocked this turn")
def _object_attacked_or_blocked(m: re.Match[str]) -> Condition:
    return _obj(m, "attacked_or_blocked")  # 508.1 / 509.1g


@_history_pattern(r"(?P<o>it|that (?:creature|permanent|token)) entered this turn")  # (~: entered_self)
def _object_entered(m: re.Match[str]) -> Condition:
    return _obj(m, "entered")


# -- counters (wave 41A) -- 700.4: "Whenever another creature you control leaves the battlefield, if it didn't die, …" (Taeko, the Patient Avalanche): it went
# somewhere other than a graveyard; the turn's departures keep where each went (Departure.to), found by the object's id, fixed once it left (603.4)
@_history_pattern(r"(?P<o>it|that (?:creature|permanent)) (?:didn't|did not) die")
def _object_didnt_die(m: re.Match[str]) -> Condition:
    return _obj(m, "died", negate=True)


@_history_pattern(rf"{_HO} enlisted a creature this combat")
def _object_enlisted(m: re.Match[str]) -> Condition:
    return _obj(m, "enlisted")  # -- trailing & intervening ifs (wave 38A) -- 702.154a: it was the attacker a creature was tapped for, in this combat phase (Aradesh)


@_history_pattern(rf"{_HO} dealt damage to another creature this turn")
def _object_dealt_creature(m: re.Match[str]) -> Condition:
    return _obj(m, "dealt_creature")  # -- commanders (wave 47A) -- Wolverine, Best There Is: some creature other than it was dealt damage by it this turn (120.3)


@_history_pattern(rf"{_HO} (?:dealt|has dealt) (?:(?P<n>\w+) or more )?(?P<kind>combat )?damage to (?P<p>a player|that player) this turn")
def _object_dealt_player(m: re.Match[str]) -> Condition | None:
    n = _num(m["n"]) if m["n"] else 1
    if n is None:
        return None
    return _obj(m, "dealt_player", n=n, **_damage_kind(m), **({"to": "event"} if m["p"] == "that player" else {}))


@_history_pattern(r"(?P<who>you|a player) (?:was|were|has been|have been) dealt (?:(?P<n>\w+) or more )?(?P<kind>combat |noncombat )?damage"
                  r"(?: by an? (?P<sub>[A-Z][a-z]+))? this turn")
def _player_dealt(m: re.Match[str]) -> Condition | None:
    n = _num(m["n"]) if m["n"] else 1  # 120.3: "you were dealt 4 or more damage" (Boarded Window), "a player was dealt combat damage by a Zombie"
    if n is None:
        return None
    out: Condition = {"history": "damage", "who": "you" if m["who"] == "you" else "any", "n": n}
    if m["kind"]:
        out["combat"] = m["kind"] == "combat "
    if m["sub"]:  # (the source's creature types as it dealt the damage, 608.2i)
        out["source"] = {"types": [], "supertypes": [], "subtypes": [m["sub"]]}
    return out


@_history_pattern(r"it(?:'s| was| is) the (?P<ord>second|third|fourth|fifth) (?P<sel>.+? )?spell you(?:'ve)? cast this turn")
def _cast_nth(m: re.Match[str]) -> Condition | None:
    key = _history_sel(f"{m['sel'] or ''}spell", "stack")
    n = ["first", "second", "third", "fourth", "fifth"].index(m["ord"]) + 1
    return None if key is None else {"history": "cast_nth", "object": "it", "who": "you", "sel": key, "n": n}  # 601.2i


@_history_pattern(r"you(?:'ve| have)? drawn more than one card this turn")
def _drew_two(m: re.Match[str]) -> Condition:
    return {"history": "drew", "n": 2}


@_history_pattern(r"(?:a|one or more) cards? (?:was|were) put into exile this turn")
def _put_into_exile(m: re.Match[str]) -> Condition:
    return {"history": "facts", "kind": "exile", "who": "any", "n": 1}  # 400.1: a card (never a token or a copy) put into exile from another zone


@_history_pattern(r"(?:a|an) (?P<sel>.+?) (?P<k>crewed|saddled) (?:it|~) this turn")
def _crewed_by(m: re.Match[str]) -> Condition | None:
    key = _history_sel(m["sel"], "battlefield")  # (702.122c: the creatures tapped to pay its crew cost, as they were then — Adrestia's ruling)
    return None if key is None else {"history": "facts", "kind": "crew" if m["k"] == "crewed" else "saddle", "who": "any", "sel": key, "of_self": True, "n": 1}


@_history_pattern(r"you(?:'ve| have)? put (?:a|an|one or more) (?:(?P<k>\S+) )?counters? on ~ this turn")
def _put_counters_on_self(m: re.Match[str]) -> Condition | None:
    if m["k"] is not None and m["k"] not in _COUNTER_KINDS:
        return None  # (122.6: the player who put them — the event's actor — against any other)
    return {"history": "facts", "kind": "counters", "who": "any", "self": True, "by": "you", "n": 1, **({"counter": m["k"]} if m["k"] else {})}
# -- end this-turn state (wave 33D) --
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
    t = re.sub(r"^(it|~|that (?:creature|permanent)) has (power|toughness|mana value) (?=\w+ or (?:less|greater|more|fewer)|exactly \w+)",  # (wave 26D; 36A: ~, "exactly")
               lambda m: f"{'its' if m[1] == 'it' else m[1] + chr(39) + 's'} {m[2]} is ", t)  # "it has power 4 or greater" = "its power is 4 or greater"
    t = re.sub(r"^it has the (least|greatest) (power|toughness) or is tied for (?:the )?(?:least|greatest) (?:power|toughness) among creatures on the battlefield$",
               r"it's a creature with the \1 \2 among creatures on the battlefield", t)  # -- extremes (wave 49C) -- Wretched Banquet: no creature has less, 608.2c (selectors "ext:")
    t = re.sub(r"^(?:it|that card) has the chosen name$", "it's a card with the chosen name", t)  # -- card names (wave 49C) -- Cursed Scroll: 201.4, the name answered earlier in the same resolution
    t = re.sub(r"^the creature had (?=(?:power|toughness|mana value) \w+ or )", "that creature had ", t)  # -- named permanents (wave 35C) -- Anax: the creature that died
    t = re.sub(r"^it had (power|toughness|mana value) (?=\w+ or )", r"its \1 was ", t)  # -- most-played cards (wave 49A) -- "If it had mana value 3 or less" (Consuming Ashes): as it last existed (608.2h)
    t = re.sub(r"^(that (?:creature|permanent|card|artifact|land|token)) had (?=(?:power|toughness|mana value) \w+ or )", r"\1's ", t)
    t = re.sub(r"^(that (?:creature|permanent|card|artifact|land|token)'s (?:power|toughness|mana value)) (\w+ or )", r"\1 was \2", t)
    t = re.sub(r"^it has the same (power|toughness|mana value) as the (discarded|revealed) card$", r"its \1 is equal to the \2 card's \1", t)  # (wave 44D: Hisoka, Minamo Sensei)
    m = _OBJECT_VS_COLORS.fullmatch(t)
    if m:  # (wave 25B) the spell's own payment record, read as it resolves
        return {"object": "it", "stat": m["stat"].replace(" ", "_"), "op": _REF_OPS[m["cmp"]], "n": {"colors_spent": 1}}
    m = _OBJECT_VS_REVEALED.fullmatch(t)
    if m:  # -- static_other sweep (wave 17C) -- "its power is less than or equal to the revealed card's power" (Titan's Presence)
        return {"object": "it", "stat": m["stat"].replace(" ", "_"), "op": _REF_OPS[m["cmp"]],
                "n": {_REF_STATS[m["ref"]]: f"cost:{m['kind']}"}}
    m = _OBJECT_VS_COUNT.fullmatch(t)
    if m and (count := values.parse_count(m["v"])) is not None:
        return {"object": "it", "stat": m["stat"].replace(" ", "_"), "op": _REF_OPS[m["cmp"]], "n": {"count_value": count}}
    m = _OBJECT_PARITY.fullmatch(t)
    if m:  # -- spell grants (wave 30T) -- "~'s power is even" (the source itself)
        return {"object": "self", "stat": m["stat"], "op": "parity", "n": int(m["p"] == "odd")}
    m = _OBJECT_STAT.fullmatch(t)
    if m:  # "its mana value was 3 or less", "its power is 4 or greater"
        n = _num(m["n"] or m["n2"] or m["n3"])
        if n is None:
            return None
        if m["n3"]:  # -- trigger other (wave 36A) -- "if its power is exactly 20" (Amalia Benavides Aguirre)
            return {"object": _stat_object(m["who"]), "stat": m["stat"].replace(" ", "_"), "op": "==", "n": n}
        cmp = m["cmp"] or m["cmp2"]
        if m["cmp2"]:  # "less than 1" is at most 0, "greater than 3" at least 4 (whole numbers)
            n += -1 if cmp in ("less", "fewer") else 1
        return {"object": _stat_object(m["who"]), "stat": m["stat"].replace(" ", "_"),
                "op": "<=" if cmp in ("less", "fewer") else ">=", "n": n}
    m = _HAD_COUNTERS.fullmatch(t)  # -- counters (wave 5H) --
    if m:
        out_c: Condition = {"object": _OBJECT_WORDS[m["who"]], "counters": m["k"] or "*"}
        return {"not": out_c} if m["neg"] else out_c
    m = _COUNT_COUNTERS.fullmatch(t)  # -- counter counts (wave 30L) --
    if m and m["k"] not in ("any", "more", "fewer") and (n := _num(m["n"] or m["f"] or m["e"])) is not None:
        return {"object": _OBJECT_WORDS[m["who"]], "counters": m["k"], "op": "==" if m["e"] else "<=" if m["f"] or m["cmp"] == "fewer" else ">=",
                "n": n - 1 if m["f"] else n}
    m = _CONTROLLED.fullmatch(t)
    if m:
        return {"object": "it", "controlled_by": "you", **({"negate": True} if m["neg"] else {})}
    if t == "that opponent has more life than another of your opponents":  # -- counters (wave 33C) -- Breena: the player the attack was declared against
        return {"defended_more_life": True}
    if t == "it entered under your control":  # -- counters (wave 33C) -- Phelia, Hallowed Respite: the object a "return it to the battlefield under its owner's control" made, now
        return {"object": "it", "controlled_by": "you", "entered": True}  # (review 33: "entered" marks the move it asks about: scripts._entered_after_delayed)
    if re.fullmatch(r"(?:this card|~) is in your graveyard", t):  # -- graveyard triggers (wave 19C) -- the source, still the object that triggered
        return {"object": "self", "test": "in_graveyard"}
    if re.fullmatch(r"(?:this card|~) is in the command zone", t):  # -- trailing & intervening ifs (wave 38A) -- Oloro: it functions there, and only while it is (113.6b)
        return {"object": "self", "test": "in_command"}
    if re.fullmatch(r"(?:this card|~) is in the command zone or on the battlefield", t):  # -- trigger other (wave 25B) -- eminence, 113.6b
        return {"object": "self", "test": "command_or_battlefield"}
    m = _HAS_KEYWORD.fullmatch(t)  # -- refused modal/conditional (wave 3R1) -- "if that creature has toxic"
    if m:  # (wave 17D: "if it didn't have decayed" / "if it had flying": as it last existed, 608.2h)
        has: Condition = {"object": _OBJECT_WORDS[m["who"]], "has": m["kw"]}
        return {"not": has} if m["neg"] else has
    m = _BEATS_SELF.fullmatch(t)  # -- intervening ifs (wave 11F) -- "if that creature has greater power or toughness than ~"
    if m:
        stats = [x for x in (m["a"], m["b"]) if x] if m["a"] else ["power"] + (["toughness"] if "toughness" in t else [])
        return {"object": "it", "beats_self": stats}
    m = _BEATS_ALL.fullmatch(t)
    if m:
        return {"object": "it", "beats_all": m["stat"]}
    if _LESS_SELF.fullmatch(t):  # -- counters (wave 33C) -- Shelinda, Yevon Acolyte: strictly less (an equal power is the "Otherwise")
        return {"object": "it", "beats_self": ["power"], "lt": True}
    m = _SAME_NAME_OF.fullmatch(t)  # -- same name (wave 32A) -- 201.2a: "if it doesn't have the same name as another creature you control or a creature card in your graveyard"
    if m:  # (Guardian Project): the object's name against the others' (selectors._same_name), as it is or as it last existed (608.2h)
        sel = selectors.parse("permanent that " + t.split(" ", 1)[1])
        return {"object": "it", "is": sel.key()} if sel is not None and sel.extras else None
    t = re.sub(r"^(it|that (?:creature|permanent|card|land|token|artifact)|the sacrificed (?:creature|permanent|artifact))'s ", r"\1 is ", t)
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
    if what in _ATTACHED or what in ("renowned", "monstrous", "saddled"):  # (wave 11F; wave 23D: saddled, 702.171b)
        test: Condition = {"object": who, **({"attached": list(_ATTACHED[what])} if what in _ATTACHED else {"designation": what})}
        return {"not": test} if negate else test
    if what in _STATES:
        past = m["verb"] in ("was", "wasn't", "was not") and what in ("tapped", "untapped", "attacking", "blocking")
        if who not in ("self", "it", "host") or (who == "it" and not past and what not in ("tapped", "untapped", "suspected")) or (
                who == "host" and (past or what not in ("tapped", "untapped", "attacking", "blocking"))):
            return None  # (an object other than the source: "it was attacking" as it last existed; -- trailing & intervening ifs (wave 38A) -- "it's tapped" / "it's suspected" as it is now, 608.2c; -- attached events (wave 40B) -- what the source is attached to, as it is now, 301.5, 303.4)
        out: Condition = {"object": who, "test": _STATES[what]}
        if who in ("it", "host"):  # -- trigger tail (wave 16C) -- 608.2h: "if it was attacking": as it is, or as it last existed; unknown fails both ways
            return {**out, "negate": True} if negate else out
    else:
        det = re.match(r"(?:a|an|another) (?P<rest>.+)", what) if what != "another" else None
        if det is not None and what.startswith("another "):
            det = re.match(r"(?P<rest>another .+)", what)
        if det is None and re.fullmatch(r"(?:white|blue|black|red|green)(?: or (?:white|blue|black|red|green))*", what):
            det = re.match(r"(?P<rest>.+)", what + " permanent")  # "it's blue": a color test, on whatever it is
        if det is None and what == "modified":  # -- trigger other (wave 50F) -- 700.9: "if it's modified" (Ian the Reckless): a counter on it, equipped, or enchanted by its controller's Aura
            det = re.match(r"(?P<rest>.+)", "modified creature")
        if det is None and re.fullmatch(r"(?:non)?(?:basic|legendary|snow)", what):  # -- damage wordings (wave 6B) --
            det = re.match(r"(?P<rest>.+)", what + " permanent")  # "If that land was nonbasic": a supertype (205.4)
        sel = selectors.parse(det["rest"]) if det else None
        if what == "all colors":  # -- trigger other (wave 44B) -- 105.2: "If that spell was all colors" (Jenson Carthalion): all five of them
            sel = selectors.Selector(extras=("all_colors:WUBRG",))
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
    if cond.get("defended_more_life"):  # -- counters (wave 33C) -- reads the player an attack trigger's event was declared against
        return True
    return any(needs_event(c) for k in ("all", "any") for c in cond.get(k, ())) or (
        "not" in cond and needs_event(cond["not"])) or (
        cond.get("versus", {}).get("who") in ("event", "defended") or cond.get("versus", {}).get("ref") in ("event", "defended"))


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
    if "defended_more_life" in cond:  # -- counters (wave 33C) -- 508.3e: the player attacked has more life than one of the controller's other opponents
        defended = (ctx.get("event") or {}).get("defended")
        return defended in plan.state.players and any(
            p not in (defended, ctx["controller"]) and plan.state.players[p].life < plan.state.players[defended].life for p in plan.live())
    if "vote" in cond:  # -- voting (wave 18C) -- this resolution's own vote (app/rules/voting.py)
        from app.rules import voting

        return voting.holds(ctx, cond)
    if "coin" in cond:  # -- coin flips (wave 7E) -- this resolution's own flip (app/rules/coin_flips.py)
        from app.rules import coin_flips

        return coin_flips.holds(ctx, cond)
    if "act7b" in cond:  # -- activation wordings (wave 7B) -- app/rules/activation_words.py
        from app.rules import activation_words

        return activation_words.holds(plan, ctx, cond)
    if "paired" in cond:  # -- soulbond (wave 24B) -- 702.95a (app/rules/pairing.py)
        from app.rules import pairing

        return pairing.holds(plan, ctx, cond)
    if "pair" in cond:  # -- merged permanents (wave 18D) --
        from app.rules import merged

        return merged.pair_holds(plan, ctx, cond["pair"])
    if "extreme" in cond:  # -- extremes (wave 8B) -- app/rules/extremes.py
        return extremes.holds(plan, ctx, cond)
    if "event_attacking" in cond:  # -- trailing & intervening ifs (wave 38A) -- 603.4: as it triggers and as it resolves
        return _event_attacking(plan, ctx, cond["event_attacking"])
    if "alone_on_player" in cond:  # -- commanders (wave 50C) -- the creature the trigger is about (an object of its event), and the player it attacks (as it last existed, 608.2h)
        refs = (ctx.get("event") or {}).get("objects") or []
        card = plan.state.cards.get(refs[0]["card"]) if refs else None
        if card is not None and plan.oid(card) == refs[0]["object_id"] and card.zone.endswith(":battlefield"):
            target = f"{card.attacking.kind}:{card.attacking.id}" if card.attacking is not None else None
        else:
            snap = plan.rules.lki.get(refs[0]["object_id"]) if refs else None
            target = snap.attack_on if snap is not None else None
        return target is not None and target.startswith("player:") and not any(
            c.id != (card.id if card is not None else "") and c.zone.endswith(":battlefield") and c.attacking is not None
            and f"{c.attacking.kind}:{c.attacking.id}" == target for c in plan.state.cards.values())
    if cond.get("static") == "life_vs_start":  # -- trailing & intervening ifs (wave 38A) -- 119.1, 903.7: read as it triggers and as it resolves (603.4)
        from app.rules import static_conditions

        return static_conditions.life_vs_start(plan, cond, ctx["controller"])
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
        if cond["turn"] == "event_player":
            from app.rules import context

            who = context.players(plan, ctx, context.EVENT)
            return len(who) == 1 and plan.state.turn.active_player == who[0]
        return plan.state.turn.active_player == ctx["controller"]
    if "status" in cond:
        return _status(plan, ctx["controller"], cond["status"])
    if "ring_other" in cond:  # -- triggers (wave 19B) -- the Ring-bearer the tempting chose (the event's ``other``), not the source
        chosen = ((ctx.get("event") or {}).get("other") or {}).get("card")
        return bool(chosen) and chosen != ctx.get("source_card")
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

        return plan.state.turn.phase in COMBAT_PHASES and (cond["combat_phase"] == "any" or plan.rules.combats == 1) \
            and (cond["combat_phase"] != "first_yours" or plan.state.turn.active_player == ctx["controller"])
    if "main_phase" in cond:  # -- combat (wave 5C) --
        return plan.state.turn.phase in ("main1", "main2") and plan.state.turn.active_player == ctx["controller"]
    v = cond["value"]
    n = values.evaluate(plan, ctx, cond["n"]) if isinstance(cond["n"], dict) else cond["n"]  # (-- counters (wave 41A) -- a count against a count: ED-E)
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
    return _OPS[cond["op"]](got, n)  # (-- counters (wave 41A) -- all of them: "prime" too)


def _attack_on_me(plan: Plan, me: str, target: str | None) -> bool:
    """Is this attack target ("player:<id>" | "card:<id>", 508.1) you, or a planeswalker you control (on the battlefield now)?"""
    kind, _, ident = (target or "").partition(":")
    if kind == "player":
        return ident == me
    walker = plan.state.cards.get(ident) if kind == "card" else None
    return walker is not None and walker.zone.endswith(":battlefield") and walker.controller == me and "Planeswalker" in plan.ch(walker).types


def _event_attacking(plan: Plan, ctx: dict[str, Any], n: int) -> bool:
    """"If two or more of those creatures are attacking you and/or planeswalkers you control" (Mangara, the Diplomat; Tomik, Wielder of Law),
    603.4: counted as the attack is declared and again as the ability resolves, over the creatures the trigger event counted (the
    event's objects). A creature still on the battlefield counts only while it is attacking you or your planeswalker (506.4: one removed from
    combat doesn't); one that left the battlefield counts as it last existed (608.2h: the player or planeswalker it was attacking, the
    ObjectSnapshot's ``attack_on``) — the rulings of 2020-06-23."""
    me, got = ctx["controller"], 0
    for ref in (ctx.get("event") or {}).get("objects") or []:
        card = plan.state.cards.get(ref["card"])
        if card is not None and plan.oid(card) == ref["object_id"] and card.zone.endswith(":battlefield"):
            target = f"{card.attacking.kind}:{card.attacking.id}" if card.attacking is not None else None
        else:
            snap = plan.rules.lki.get(ref["object_id"])
            target = snap.attack_on if snap is not None else None
        got += _attack_on_me(plan, me, target)
    return got >= n


def _status(plan: Plan, you: str, kind: str) -> bool:
    if kind == "monarch":  # 724: the monarch designation
        return plan.state.table.monarch == you
    if kind == "initiative":  # 726
        return plan.state.table.initiative == you
    if kind == "own_exiled":  # -- activated other (wave 21E) -- 108.3: a card's owner, in whichever player's exile zone it is
        return any(c.owner == you and c.zone.endswith((":exile", ":foretell")) for c in plan.state.cards.values() if c.ability is None)
    if kind != "city_blessing":  # -- counters & designations (wave 3E) --
        from app.rules import designations

        return designations.status(plan, you, kind)
    from app.rules import designations

    return bool(plan.state.players[you].city_blessing) or designations.ascend_permanent_due(plan, you)  # 702.131c ascend: the city's blessing (702.131b: at once; wave 45A)


def _versus(plan: Plan, ctx: dict[str, Any], spec: dict[str, Any]) -> bool:
    """Some one opponent's quantity compared with yours ("an opponent controls more lands than you"):
    the same quantity read for each of them (as "you" of that quantity). ``who`` (wave 11F): that one player instead."""
    if spec.get("ref"):  # -- if you do (wave 21C) -- the quantity of that one player (event / defending), not the controller's
        ref = _as_players(plan, ctx, spec["ref"])
        if len(ref) != 1:
            return False
        mine = values.evaluate(plan, {**ctx, "controller": ref[0]}, spec["value"])
    else:
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
    every = all if cond.get("every") else any  # (-- hideaway (wave 29D) -- "each player has no cards in hand")
    return every(holds(plan, {**ctx, "controller": p}, cond["cond"]) for p in players)


def _object_holds(plan: Plan, ctx: dict[str, Any], cond: Condition) -> bool:
    """A test of one object ("it's a land card"): its characteristics as it is now while it is still
    that object where it was, else as it last existed (608.2h); an object that can't be found
    fails the test (608.2b: a part that needs the information can't be carried out)."""
    who = cond["object"]
    if "controlled_by" in cond:  # -- static_other sweep (wave 17C) -- the controller it had: as it is, or as it last existed (608.2h)
        found = values._object(plan, ctx, who)
        return found is not None and (found[0].controller == ctx["controller"]) != bool(cond.get("negate"))
    if "test" in cond and who == "self":
        return _self_state(plan, ctx, cond["test"]) != bool(cond.get("negate"))  # (wave 16C: "it wasn't blocking", bound to the source)
    got = values._object(plan, ctx, who)
    if "test" in cond:  # -- trigger tail (wave 16C) -- 608.2h: the object's physical state as it is while it's still on the battlefield, else
        card = got[0] if got is not None else None  # as it last existed there (the snapshot taken as it left); not found: fails
        if card is None:
            return False
        live = plan.state.cards.get(card.id)
        if live is not None and live.zone.endswith(":battlefield"):
            state = {"tapped": live.tapped, "untapped": not live.tapped, "attacking": live.attacking is not None,
                     "blocking": bool(live.blocking), "suspected": plan.oid(live) in plan.rules.suspected}  # (suspected: wave 38A, 701.60)
        else:
            snap = next((x for x in reversed(plan.rules.lki.values()) if x.card == card.id and x.zone.endswith(":battlefield")), None)
            if snap is None:
                return False
            state = {"tapped": snap.tapped, "untapped": not snap.tapped, "attacking": snap.attacking, "blocking": snap.blocking}
        return cond["test"] in state and state[cond["test"]] != bool(cond.get("negate"))  # (a state not known as it last existed: fails both ways)
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
        if cond["designation"] == "saddled":  # -- crew & saddle (wave 23D) -- 702.171b: until end of turn (this turn's log)
            from app.rules import crew_saddle

            return crew_saddle.is_saddled(plan, card)
        return plan.oid(card) in (plan.rules.monstrous if cond["designation"] == "monstrous" else plan.rules.renowned)
    if "beats_all" in cond:  # -- most-played cards (wave 43B) -- strictly greater than every other creature on the battlefield (Selvala ruling 2016-08-23: ties draw nothing)
        stat = values._stat_of(ch, cond["beats_all"])
        if stat is None:
            return False
        others = [values._stat_of(plan.ch(c), cond["beats_all"]) for c in plan.state.cards.values()
                  if c.id != card.id and c.zone.endswith(":battlefield") and plan.in_game(c) and plan.ch(c).is_creature]
        return all(o is None or stat > o for o in others)
    if "beats_self" in cond:  # "its power is greater than ~'s": either stat named (as it is, or as it last existed, 608.2h)
        mine = values._object(plan, ctx, "self")
        if mine is None:
            return False
        pairs = [(values._stat_of(ch, st), values._stat_of(mine[1], st)) for st in cond["beats_self"]]
        return any(a is not None and b is not None and (a < b if cond.get("lt") else a > b) for a, b in pairs)
    if "counters" in cond:  # -- counters (wave 5H) -- as it is, or as it last existed (603.10a)
        kind = cond["counters"]
        if "op" in cond:  # -- counter counts (wave 30L) -- how many (122.1)
            have = card.counters.get(kind, 0)
            return have >= cond["n"] if cond["op"] == ">=" else have <= cond["n"] if cond["op"] == "<=" else have == cond["n"]
        return any(v > 0 for v in card.counters.values()) if kind == "*" else card.counters.get(kind, 0) > 0
    if "has" in cond:  # -- refused modal/conditional (wave 3R1) --
        return cond["has"] in ch.keywords
    if "stat" in cond:  # "its mana value was 3 or less": a characteristic, as it is or as it last existed (608.2h)
        value = values._stat_of(ch, cond["stat"])
        if cond["stat"] == "mana_value":  # (wave 16D) a spell on the stack counts its X (202.3e)
            from app.rules.stack_interaction import mana_value

            value = mana_value(card, ch)
        bound: Any = cond["n"]
        if isinstance(bound, dict) and "colors_spent" in bound:  # (wave 25B) converge, 202.3 / 601.2h: the colors of mana spent to cast the spell
            bound = values.evaluate(plan, ctx, bound)
        elif isinstance(bound, dict) and "count_value" in bound:  # (wave 26A) a count of the table, read as the spell resolves
            bound = values.evaluate(plan, ctx, bound["count_value"])
        elif isinstance(bound, dict):  # -- static_other sweep (wave 17C) -- the card a spell's cost revealed
            bound = values.evaluate(plan, ctx, bound) if values._object(plan, ctx, next(iter(bound.values()))) is not None else None  # (wave 44D: also "cost:discarded")
        return value is not None and bound is not None and bool(_OPS[cond["op"]](value, bound))
    # "it's a land card" / "that creature is a Human": its characteristics, wherever it is (a card in
    # a library, a graveyard or exile, or a permanent as it last existed): the zone is not the test
    sel = replace(selectors.from_key(cond["is"]), zones=(card.zone.rsplit(":", 1)[-1],))
    hit = selectors.matches(plan, sel, card, ch, ctx["controller"], ctx.get("source_card"))
    return not hit if cond.get("negate") else hit


def _self_state(plan: Plan, ctx: dict[str, Any], test: str) -> bool:
    """The source's own physical state ("~ is tapped"): as it is while it's still that object on the
    battlefield, else as it last existed there (608.2h)."""
    card = plan.state.cards.get(ctx.get("source_card") or "")
    if test == "in_graveyard":  # -- graveyard triggers (wave 19C) -- 400.7: a card that left is a new object, which isn't there
        return card is not None and card.zone == f"{card.owner}:graveyard" and plan.oid(card) == ctx.get("source_object")
    if test == "solved":  # -- Case (wave 51C) -- 719.3b: the designation is the permanent's "Solved" choice, gone when it leaves the battlefield (400.7)
        return card is not None and card.zone.endswith(":battlefield") and plan.oid(card) == ctx.get("source_object") and "Solved" in card.choices
    if test == "on_battlefield":  # -- reanimation Auras (wave 51F) -- 603.4: "if it's on the battlefield" as the ability resolves: still that object (400.7)
        return card is not None and card.zone.endswith(":battlefield") and plan.oid(card) == ctx.get("source_object")
    if test == "in_command":  # -- trailing & intervening ifs (wave 38A) -- still that object, in the command zone (400.7): a commander cast in response is a new object
        return card is not None and card.zone.endswith(":command") and plan.oid(card) == ctx.get("source_object")
    if test == "command_or_battlefield":  # -- trigger other (wave 25B) -- eminence: 113.6b, the zones the ability names (still that object, 400.7)
        return card is not None and card.zone.endswith((":command", ":battlefield")) and plan.oid(card) == ctx.get("source_object")
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
        if test in ("suspected", "prepared", "attached_to"):
            return False
    if test == "attached_to":  # -- casting extras (wave 18E) -- attached to a permanent that's on the battlefield (a creature, as only one can be)
        host = plan.state.cards.get(card.attached_to or "") if card is not None else None
        return host is not None and host.zone.endswith(":battlefield")
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
_CAST = re.compile(rf"(?:(?P<you>you) (?P<neg>didn't )?cast (?P<who>{_CAST_SUBJECT})|(?P<who2>{_CAST_SUBJECT}) (?P<neg2>wasn't|was) cast)"
                   r"(?: from (?P<from>your hand|a graveyard|your graveyard|exile|your library|anywhere other than your hand))?"
                   r"(?P<main> during your main phase)?")
_SPENT_SYMBOLS = re.compile(rf"(?P<syms>(?:\{{[WUBRGCS]\}})+) was spent to cast (?P<who>{_CAST_SUBJECT})")  # ({S}: wave 18B)
# -- mana provenance (wave 18B) -- 106.3, 107.4h: "if mana from a Treasure was spent to cast it", "if three or more mana from creatures was
# spent to cast it": the mana spent that a source with that type produced (PaymentRecord.mana_tags, app/rules/mana_units.py)
_FROM_TAGS = {"treasure": "Treasure", "treasures": "Treasure", "creature": "Creature", "creatures": "Creature", "artifact": "Artifact",
              "artifacts": "Artifact", "desert": "Desert", "cave": "Cave", "snow": "Snow"}
_SPENT_FROM = re.compile(rf"(?:(?:at least )?(?P<n>\w+)(?: or more)? )?mana from (?:(?:a|an) )?(?P<what>[a-z]+)(?: source)?"
                         rf" (?:was|were) spent to cast (?P<who>{_CAST_SUBJECT}|that spell)")
_SPENT_COLOR = re.compile(rf"at least (?P<n>\w+) (?P<color>white|blue|black|red|green|colorless) mana was spent to cast (?P<who>{_CAST_SUBJECT})")
_SPENT_SAME = re.compile(rf"at least (?P<n>\w+) mana of the same color was spent to cast (?P<who>{_CAST_SUBJECT})")
_SPENT_TOTAL = re.compile(rf"(?P<n>\w+) or more mana was spent to cast (?P<who>{_CAST_SUBJECT})")
_COLOR_LETTER = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G", "colorless": "C"}  # (wave 22E: colorless, 107.4)
_FROM = {"your hand": "hand", "a graveyard": "graveyard", "your graveyard": "graveyard", "exile": "exile",
         "your library": "library", "anywhere other than your hand": "!hand"}


def _cast_who(word: str) -> str:
    return "it" if word == "it" else "self"


# -- counters (wave 33C) -- some one of the objects an aggregated trigger ("one or more creatures you control enter") is about, 603.2c
_SOME_OF_THEM = re.compile(r"one or more of them entered from a graveyard(?: or (?:was|were) cast from (?P<b>a graveyard))?")
_NO_MANA = re.compile(r"no mana was spent to cast (?:it|that spell)")  # -- if you do (wave 5G) --
# -- ability words (wave 9C) -- opus: "If five or more mana was spent to cast that spell, …" (a cast trigger's spell)
_SPENT_TOTAL_THAT = re.compile(r"(?P<n>\w+) or more mana was spent to cast that spell")
_SPENT_OVER_PT = re.compile(r"the amount of mana you spent is greater than (?:this creature's|~'s) power or toughness")  # (increment, wave 16B)


def _cast_how(t: str) -> Condition | None:
    """A condition about how the source was cast, or None."""
    if t in ("the gift was promised", "its gift cost was paid", "this spell's gift cost was paid"):  # -- gift (wave 23D) -- 702.174k: read as kicked
        return {"object": "self", "cast": {"kicked": True}}
    if t == "evidence was collected":  # -- casting costs (wave 22F) -- 701.59a: the spell's optional additional cost, announced as it was cast
        return {"object": "self", "cast": {"optional": "evidence"}}
    if t in ("this spell's additional cost was paid", "its additional cost was paid"):  # -- blight (wave 51E) -- 701.68a: the one optional additional cost a spell prints
        return {"object": "self", "cast": {"optional": "blight"}}
    if re.fullmatch(r"an? [a-z]+ was beheld", t):  # 701.4a: "If a Dragon was beheld" (the only behold cost on the spell)
        return {"object": "self", "cast": {"optional": "behold"}}
    if t in ("this spell was cast using teamwork", "it was cast using teamwork"):  # -- static_other sweep (wave 17C) -- 702.194b
        return {"object": "self", "cast": {"optional": "teamwork"}}
    if t in ("this spell's prowl cost was paid", "its prowl cost was paid"):  # -- static_other sweep (wave 17C) -- 702.76a
        return {"object": "self", "cast": {"alt": "prowl"}}
    if (m := re.fullmatch(r"(?:(?:this spell's|this creature's|its|his|her) (?P<k>mayhem|web-slinging|sneak|surge|spectacle|emerge) cost was paid(?P<turn> this turn)?|(?P<w>it|this spell|~|they) (?:was|were) cast "
                          r"using (?P<k2>mayhem|web-slinging))", t)) is not None:  # -- Marvel keywords (wave 25A; sneak: 30I) -- 702.187b, 702.188a, 702.190a
        # (-- static_other (wave 36B) -- surge 702.117a, spectacle 702.137a, emerge 702.119a: the cast record's alternative is the keyword (alt_costs.keyword_definition))
        return {"object": _cast_who(m["w"] or "self"), "cast": {"alt": m["k"] or m["k2"], **({"this_turn": True} if m["turn"] else {})}}
    if re.fullmatch(r"the (?:\{[^}]+\})+ cost was paid", t):  # -- static_other (wave 36B) -- "If the {1}{B} cost was paid" (Baleful Mastery): the one alternative cost the card prints (118.9a)
        return {"object": "self", "cast": {"alt": "alternative"}}
    if t in ("this spell was foretold", "it was foretold"):  # -- hidden exile (wave 18A) -- 702.143c: cast for its foretell cost (the only way)
        return {"object": _cast_who(t.split()[0]), "cast": {"alt": "foretell"}}
    if t in ("it was kicked", "this spell was kicked", "~ was kicked"):  # -- kicked instead (wave 20F) -- 702.33d: "When you cast this
        return {"object": _cast_who(t.split()[0]), "cast": {"kicked": True}}  # spell, if it was kicked, …" (its record, 601.2h)
    if t == "tribute wasn't paid":  # -- keywords (wave 50H) -- 702.104b (app/rules/tribute.py)
        return {"object": "self", "cast": {"tribute": False}}
    if t in ("it wasn't kicked", "~ wasn't kicked"):  # -- trailing & intervening ifs (wave 38A) -- "Then if it wasn't kicked, discard three cards." (Sphinx of Lost Truths): the same record, 702.33d
        return {"not": {"object": _cast_who(t.split()[0]), "cast": {"kicked": True}}}
    if t in ("it escaped", "~ escaped"):  # -- escape (wave 5I) -- 702.138b
        return {"object": _cast_who(t.split()[0]), "cast": {"escaped": True}}
    if _NO_MANA.fullmatch(t):  # -- if you do (wave 5G) -- "if no mana was spent to cast it" (a cast trigger's spell)
        return {"object": "it", "cast": {"no_mana": True}}
    t = re.sub(r"^at least (\w+) mana was spent", r"\1 or more mana was spent", t)  # (wave 11F: the same thing)
    if (m := _SPENT_TOTAL_THAT.fullmatch(t)) is not None and (n := _num(m["n"])):  # -- ability words (wave 9C) -- opus
        return {"object": "it", "cast": {"total": n, "event_spell": True}}
    if t == "the amount of mana spent to cast it was less than its mana value":  # -- triggers (wave 21B) -- the cast spell's total cost vs its mana value
        return {"object": "it", "cast": {"total": "under_mv", "event_spell": True}}
    if _SPENT_OVER_PT.fullmatch(t):  # -- static_other sweep (wave 16B) -- increment: more than the source's power or toughness (702.190a)
        return {"object": "it", "cast": {"total": "over_min_pt", "event_spell": True}}
    if re.fullmatch(r"the amount of mana spent to cast (?:it|that spell) is greater than (?:~|this creature)'s power", t):  # (wave 45D: Liberator) the amount actually spent (ruling 2022-10-14)
        return {"object": "it", "cast": {"total": "over_power", "event_spell": True}}
    m = _SOME_OF_THEM.fullmatch(t)
    if m:  # -- counters (wave 33C) -- Celes, Kotis: "if one or more of them entered from a graveyard or was cast from a graveyard" (an aggregated enter)
        parts: list[Condition] = [{"object": "event", "each": "any", "cast": {"entered_from": "graveyard"}}]
        if m["b"]:
            parts.append({"object": "event", "each": "any", "cast": {"from": "graveyard"}})
        return {"any": parts} if m["b"] else parts[0]
    if (m := re.fullmatch(r"(?P<w>it|~) entered from your library or was cast from your library", t)) is not None:
        # -- named permanents (wave 35C) -- Fblthp: put onto the battlefield from the library, or cast from it (it enters from the stack then: 400.7, 601.2a)
        who = _cast_who(m["w"])
        return {"any": [{"object": who, "cast": {"entered_from": "your library"}}, {"object": who, "cast": {"by_you": False, "from": "library"}}]}
    if t == "none of them were cast or no mana was spent to cast them":  # -- trigger other (wave 51E) -- Satoru, the Infiltrator: every object of an aggregated enter
        return {"object": "event", "cast": {"none_paid": True}}
    if t == "it wasn't put onto the battlefield with this ability":  # -- trigger other (wave 51E) -- Kodama of the East Tree: Entry.via (the source's own effect)
        return {"object": "it", "cast": {"put_by_this": False}}
    m = re.fullmatch(r"(?P<who>it|~|this creature|that creature) entered from (?P<z>your graveyard|a graveyard|exile|your hand)", t)
    if m:  # -- history (wave 22E) -- Archfiend's Vessel: "if it entered from your graveyard or you cast it from your graveyard"
        return {"object": "it" if m["who"] in ("it", "that creature") else "self", "cast": {"entered_from": m["z"].replace("a ", "")}}
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
        found_cast: Condition = {"object": _cast_who(m["who"] or m["who2"]), "cast": how}
        # -- trigger tail (wave 16C) -- "if you didn't cast it from your hand": no record (put onto the battlefield) or another zone
        return {"not": found_cast} if m["neg"] or m["neg2"] == "wasn't" else found_cast
    if (m := _SPENT_FROM.fullmatch(t.lower())) is not None and m["what"] in _FROM_TAGS and (m["n"] is None or _num(m["n"])):
        how_from: dict[str, Any] = {"from_mana": {"tag": _FROM_TAGS[m["what"]], "n": _num(m["n"]) if m["n"] else 1}}
        if m["who"] == "that spell":  # a cast trigger's spell (trigger_words rewrites its "it")
            return {"object": "it", "cast": {**how_from, "event_spell": True}}
        return {"object": _cast_who(m["who"]), "cast": how_from}
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
        # (-- history (wave 22E) -- the trigger's own object too: "if it wasn't cast", "if you didn't cast it from your hand" - a
        # permanent keeps its spell's record under its own object id (engine.leave_stack), for as long as it, or its last known
        # information, exists)
        return cond.get("object") in ("self", "event")
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
    if "tribute" in how:  # -- keywords (wave 50H) -- 702.104b: true unless the chosen opponent had it enter with the counters (a fact about the object, kept in RulesState)
        return (ctx.get("source_object") or "") not in plan.rules.tribute_paid
    if cond.get("each") == "any":  # -- counters (wave 33C) -- "if one or more of them …": some object of the event's batch
        event = ctx.get("event") or {}
        one = {k: v for k, v in cond.items() if k != "each"}
        return any(_cast_holds(plan, {**ctx, "event": {**event, "objects": [r]}}, one) for r in event.get("objects") or [])
    if "entered_from" in how:  # -- history (wave 22E) -- "if it entered from your graveyard": where this turn's entry came from
        from app.rules import context, history

        refs = context._object_refs(ctx, context.EVENT) if cond.get("object") == "event" else []
        oid = refs[0].object_id if refs else ctx.get("source_object") if cond.get("object") == "self" else None
        return history.entry_came_from(plan, oid, how["entered_from"], ctx["controller"])
    if how.get("none_paid"):  # -- trigger other (wave 51E) -- each object either wasn't cast or had no mana spent on it (a cast by hand: not known, so it never holds, as _no_mana_spent)
        from app.rules import context

        recs = [plan.rules.payments.get(r.object_id) for r in context._object_refs(ctx, context.EVENT)]
        return all(r is None or r.cast_from is None or (r.mana_known and sum(r.mana_spent.values()) == 0) for r in recs)
    if "put_by_this" in how:  # -- trigger other (wave 51E) -- the entry of the object the event is about, put there by this source's effect (Kodama)
        from app.rules import context, history

        refs = context._object_refs(ctx, context.EVENT)
        return any(e.object_id == (refs[0].object_id if refs else None) and e.via == ctx.get("source_object")
                   for e in history.log_for(plan).entered) == how["put_by_this"]
    if cond.get("object") == "event" and how.get("no_mana"):  # -- if you do (wave 5G) --
        return _no_mana_spent(plan, ctx)
    if cond.get("object") == "event" and how.get("event_spell"):  # -- ability words (wave 9C) -- opus
        if "from_mana" in how:  # -- mana provenance (wave 18B) -- "if mana from a Treasure was spent to cast it" (a cast trigger)
            return _mana_from_event(plan, ctx, how["from_mana"])
        return _total_mana_spent(plan, ctx, how["total"])
    if cond.get("object") == "event":  # -- history (wave 22E) -- the object the trigger's event was about, and how it was cast
        from app.rules import context

        refs = context._object_refs(ctx, context.EVENT)
        record = plan.rules.payments.get(refs[0].object_id) if refs else None
    elif cond.get("object") == "self":
        record = plan.rules.payments.get(ctx.get("source_object") or "")
    else:
        return False
    if record is None or record.cast_from is None:
        return False
    if how.get("by_you") and record.controller != ctx["controller"]:
        return False
    if how.get("kicked") and not record.kicked:  # 702.33d (a modal header's "If it was kicked, choose both instead")
        return False
    if how.get("escaped") and record.alternative != "escape":  # -- escape (wave 5I) -- 702.138b
        return False
    if how.get("optional") and f"optional:{ctx.get('source_card')}:{how['optional']}" not in record.additional:
        return False  # -- static_other sweep (wave 17C) -- teamwork 702.194b: the caster declared paying it
    if how.get("alt") and record.alternative != how["alt"]:  # -- static_other sweep (wave 17C) -- "if this spell's prowl cost was paid"
        return False
    if how.get("this_turn"):  # -- keywords (wave 30I) -- "if her sneak cost was paid this turn": the permanent's spell was cast this turn (history)
        from app.rules import history

        if not any(n.became == ctx.get("source_object") for n in history.log_for(plan).casts):
            return False
    zone = how.get("from")
    if zone is not None and (record.cast_from == zone[1:] if zone.startswith("!") else record.cast_from != zone):
        return False
    if how.get("main") and not record.cast_main:
        return False
    if any(k in how for k in ("spent", "same_color", "total", "from_mana")) and not record.mana_known:
        return False  # (cast by hand: what paid for it isn't known — such a condition never holds)
    spent = record.mana_spent
    if any((sum(1 for t in record.mana_tags if "Snow" in t) if sym == "S" else spent.get(sym, 0)) < n  # ({S}: 107.4h)
           for sym, n in (how.get("spent") or {}).items()):
        return False
    if "from_mana" in how and sum(1 for t in record.mana_tags if how["from_mana"]["tag"] in t) < how["from_mana"]["n"]:
        return False
    if "same_color" in how and not any(spent.get(c, 0) >= how["same_color"] for c in "WUBRG"):
        return False
    return "total" not in how or sum(spent.values()) >= how["total"]
# -- end refused modal/conditional (wave 3R1) --


# -- mana provenance (wave 18B) --
def _mana_from_event(plan: Plan, ctx: dict[str, Any], need: dict[str, Any]) -> bool:
    """"Whenever you cast a spell, if mana from a Treasure was spent to cast it, …": the cast spell's payment record, read while it is
    on the stack (603.4). A spell cast by hand has no known payment: the condition doesn't hold (said in the log)."""
    from app.rules import context

    refs = context._object_refs(ctx, context.EVENT)
    record = plan.rules.payments.get(refs[0].object_id) if refs else None
    if record is None or record.cast_from is None:
        return False
    if not record.mana_known:
        plan.note(f"{plan.state.cards[record.card].name or 'That spell'} was cast by hand: what paid for it isn't known — apply the "
                  "ability by hand", [record.card])
        return False
    return sum(1 for t in record.mana_tags if need["tag"] in t) >= need["n"]


# -- ability words (wave 9C) --
def _total_mana_spent(plan: Plan, ctx: dict[str, Any], need: int | str) -> bool:
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
    if need == "under_mv":  # -- triggers (wave 21B) -- 202.3b: an X spell's mana value on the stack counts X (review (wave 21): 202.3e,
        from app.rules.stack_interaction import mana_value  # as "that spell's mana value" reads it)

        spell = plan.state.cards.get(record.card)
        return spell is not None and sum(record.mana_spent.values()) < mana_value(spell, plan.ch(spell))
    if need in ("over_min_pt", "over_power"):  # increment: strictly more than the smaller of the source's power and toughness (as it is now, 603.4); (wave 45D) Liberator: its power
        src = plan.state.cards.get(ctx.get("source_card") or "")
        if src is None or not src.zone.endswith(":battlefield"):
            return False
        ch = plan.ch(src)
        stats = [s for s in (values._stat_of(ch, "power"), None if need == "over_power" else values._stat_of(ch, "toughness")) if s is not None]
        return bool(stats) and sum(record.mana_spent.values()) > min(stats)
    return sum(record.mana_spent.values()) >= int(need)


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

