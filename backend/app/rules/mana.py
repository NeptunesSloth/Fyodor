"""Mana: costs, mana abilities, and paying for things.

* ``parse_cost("{2}{G}{G}")`` → a ``ManaCost``.
* ``parse_mana_ability("{T}: Add {R} or {G}.")`` → what a mana ability produces, or ``None`` when
  the wording isn't one the engine understands (the ability then stays a manual one).
* ``solve(cost, pool, sources)`` finds a way to pay: mana already in the pool first, then untapped
  sources, preferring the least flexible ones so dual lands and "any color" sources are kept for
  last (roughly what Arena's auto-payment does).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from itertools import combinations_with_replacement
from typing import Any

from app.rules import mana_riders as _mana_riders  # -- mana riders (wave 5A) --

COLORS = ("W", "U", "B", "R", "G")
ALL_MANA = (*COLORS, "C")
_SYMBOL = re.compile(r"\{([^}]+)\}")
_COST_AND_EFFECT = re.compile(r"^(?P<cost>[^:]+): (?P<effect>(?:Choose a color\. )?Add .+)$")


class ManaError(ValueError):
    pass


@dataclass(frozen=True)
class ManaCost:
    generic: int = 0
    colored: tuple[str, ...] = ()  # one entry per coloured symbol, e.g. ("G", "G"); "C" = specifically colourless
    hybrid: tuple[tuple[str, ...], ...] = ()  # each: acceptable colours; ("2", "B") = two generic or {B}
    phyrexian: tuple[str, ...] = ()  # colours payable with mana or 2 life
    x: int = 0  # number of {X}
    unsupported: tuple[str, ...] = ()  # symbols the engine can't pay (e.g. {S} snow)

    def with_x(self, x: int) -> ManaCost:
        return ManaCost(self.generic + x * self.x, self.colored, self.hybrid, self.phyrexian, 0, self.unsupported)

    def plus_generic(self, n: int) -> ManaCost:
        return ManaCost(self.generic + n, self.colored, self.hybrid, self.phyrexian, self.x, self.unsupported)

    def text(self) -> str:
        parts = [f"{{{self.generic}}}"] if self.generic else []
        parts += ["{X}"] * self.x
        parts += [f"{{{c}}}" for c in self.colored]
        parts += ["{" + "/".join(h) + "}" for h in self.hybrid]
        parts += [f"{{{c}/P}}" for c in self.phyrexian]
        return "".join(parts) or "{0}"

    @property
    def is_free(self) -> bool:
        return not (self.generic or self.colored or self.hybrid or self.phyrexian or self.x)


def parse_cost(text: str | None) -> ManaCost:
    generic = x = 0
    colored: list[str] = []
    hybrid: list[tuple[str, ...]] = []
    phyrexian: list[str] = []
    unsupported: list[str] = []
    for sym in _SYMBOL.findall(text or ""):
        if sym.isdigit():
            generic += int(sym)
        elif sym == "X":
            x += 1
        elif sym in ALL_MANA:
            colored.append(sym)
        elif sym.endswith("/P") and sym[0] in COLORS:
            phyrexian.append(sym[0])
        elif "/" in sym:
            hybrid.append(tuple(sym.split("/")))
        else:
            unsupported.append(sym)
    return ManaCost(generic, tuple(colored), tuple(hybrid), tuple(phyrexian), x, tuple(unsupported))


@dataclass(frozen=True)
class ManaAbility:
    """A mana ability the engine understands (CR 605).

    ``options`` are the mana combinations it can add. Special entries resolved against the table:
    ``("CHOSEN",)`` (the permanent's chosen color), ``("LANDS",)`` / ``("LANDS_OPP",)`` (a type of
    mana that a land you control / an opponent controls could produce).
    """

    tap: bool
    sacrifice_self: bool
    options: tuple[tuple[str, ...], ...]  # each option: the mana it adds, e.g. ("C", "C") or ("R",)
    extra_cost: str = ""  # other activation costs: mana ("{1}"), "Pay N life", "Remove a … counter …"
    riders: tuple[tuple[str, int], ...] = ()  # ("damage", n) to its controller, ("draw", n)
    spend_only: str | None = None  # "creature", "instant_sorcery", "artifact", "ability", "type:<T>", …
    once_per_turn: bool = False
    condition: str | None = None  # "control:<subtype or type>"
    count: str | None = None  # each option is repeated N times: "control:<type>" (for each … you control), "power"
    # -- refused copy/mana (wave 3R3) -- a cost part that chooses objects ("Sacrifice a creature", Ashnod's Altar):
    # activated by hand only (the payer chooses, app/rules/cost_payment.py), never by the auto-payer
    chooses: bool = False
    # -- refused copy/mana (wave 3R3) -- "If you control an Urza's Mine and an Urza's Power-Plant, add {C}{C}{C}
    # instead." (Urza's Tower): the permanents (each a set of subtypes) that must all be controlled, and the options
    # that replace ``options`` then (614.1a: an "instead" of the ability's own effect, checked as it resolves)
    instead_if: tuple[tuple[str, ...], ...] = ()
    instead: tuple[tuple[str, ...], ...] = ()
    # -- refused copy/mana (wave 3R3) -- "Put a -0/-1 counter on this creature: Add {G}." (Wall of Roots): the
    # counter put on the source as the cost (by hand only: the auto-payer never weakens a creature)
    self_counter: str | None = None

    @property
    def penalty(self) -> int:
        """How much using it costs beyond tapping (the payer avoids painful options first)."""
        return sum(n for kind, n in self.riders if kind == "damage") * 3 + (5 if self.extra_cost else 0) + (4 if self.sacrifice_self else 0) \
            + _mana_riders.penalty(self.riders)  # -- mana riders (wave 5A) --


_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_N = r"(one|two|three|four|five|six|seven|eight|nine|ten)"


def _effect_options(effect: str, identity: tuple[str, ...]) -> tuple[tuple[str, ...], ...] | None:
    effect = effect.strip().rstrip(".")
    if effect == "Add one mana of any color":
        return tuple((c,) for c in COLORS)
    if effect == "Add one mana of any color in your commander's color identity":
        return tuple((c,) for c in COLORS if c in identity)
    if m := re.fullmatch(rf"Add {_N} mana of any one color", effect):
        n = _NUM[m.group(1)]
        return tuple((c,) * n for c in COLORS)
    if m := re.fullmatch(rf"Add {_N} mana in any combination of colors", effect):
        return tuple(combinations_with_replacement(COLORS, _NUM[m.group(1)]))
    if m := re.fullmatch(rf"Add {_N} mana in any combination of \{{([WUBRGC])\}} and/or \{{([WUBRGC])\}}", effect):
        return tuple(combinations_with_replacement((m.group(2), m.group(3)), _NUM[m.group(1)]))
    if m := re.fullmatch(rf"Add {_N} mana of the chosen color", effect):
        return (("CHOSEN",) * _NUM[m.group(1)],)
    if m := re.fullmatch(r"Add \{([WUBRGC])\} or one mana of the chosen color", effect):
        return ((m.group(1),), ("CHOSEN",))
    if m := re.fullmatch(rf"Add {_N} \{{([WUBRGC])\}}", effect):  # -- wave 3R3: "Add six {G}" (Castle Garenbrig) --
        return ((m.group(2),) * _NUM[m.group(1)],)
    if effect == "Add one mana of any type that a land you control could produce":
        return (("LANDS",),)
    if effect == "Add one mana of any color that a land an opponent controls could produce":
        return (("LANDS_OPP",),)
    body = effect[len("Add "):]
    if not body.startswith("{"):
        return None
    # "{R} or {G}" / "{W}, {U}, or {B}" → one symbol each; "{C}{C}" / "{G}{G}" → one option
    if " or " in body or ", " in body:
        pieces = [p.strip() for p in re.split(r",? or |, ", body) if p.strip()]
        if all(re.fullmatch(r"(\{[WUBRGC]\})+", p) for p in pieces):
            return tuple(tuple(_SYMBOL.findall(p)) for p in pieces)
        return None
    if re.fullmatch(r"(\{[WUBRGC]\})+", body):
        return (tuple(_SYMBOL.findall(body)),)
    return None


_SPEND = [
    (re.compile(r"^Spend this mana only to cast (a |an )?creature spells?$"), "creature"),
    (re.compile(r"^Spend this mana only to cast (an )?instant or sorcery spells?$"), "instant_sorcery"),
    (re.compile(r"^Spend this mana only to cast (an )?artifact spells?$"), "artifact"),
    (re.compile(r"^Spend this mana only to activate abilities$"), "ability"),
    (re.compile(r"^Spend this mana only to cast (an )?artifact spells? or activate (an )?abilit(y|ies) of (an )?artifacts?( sources?)?$"),
     "artifact_or_artifact_ability"),
    (re.compile(r"^Spend this mana only to cast (a )?legendary spells?$"), "legendary"),
    (re.compile(r"^Spend this mana only to cast (a |an )?(?P<t>[A-Z][a-z]+) (creature )?spells?$"), "type"),
    # -- mana (wave 3M): restrictions the payer can enforce (casting.spend_allowed) --
    (re.compile(r"^Spend this mana only to cast colorless Eldrazi spells or activate abilities of colorless Eldrazi$"), "colorless_eldrazi"),
    (re.compile(r"^This mana can't be spent to cast (a nonartifact spell|nonartifact spells)$"), "not_nonartifact_spell"),
]
_DAMAGE_YOU = re.compile(r"^(This \w+|[A-Z][^.]{0,60}?) deals (?P<n>\d+) damage to you$")
_CONTROL = re.compile(r"^Activate only if you control an? (?P<what>[A-Z][a-z]+)(?: or an? (?P<or>[A-Z][a-z]+))?$")
# -- mana (wave 3M) -- "Activate only if you control five or more lands"; "for each charge counter on this artifact"
_CONTROL_COUNT = re.compile(rf"^Activate only if you control {_N} or more (?P<what>lands|creatures|artifacts|enchantments)$")
_COUNTERS_FOR_EACH = re.compile(r"^Add \{(?P<sym>[WUBRGC])\} for each (?P<kind>[a-z]+) counter on (?:this \w+|~)$")
_FOR_EACH = re.compile(r"^Add \{(?P<sym>[WUBRGC])\} for each (?P<what>creature|artifact|enchantment|land|[A-Z][a-z]+) you control$")
_COUNT_TYPES = {"creature": "Creature", "artifact": "Artifact", "enchantment": "Enchantment", "land": "Land"}
_POWER_OF = re.compile(r"^Add an amount of \{(?P<sym>[WUBRGC])\} equal to (?:this creature|[A-Z][^.]{0,60}?)'s power$")
_X_POWER = re.compile(r"^Add X mana of any one color, where X is (?:this creature|[A-Z][^.]{0,60}?)'s power$")
# -- X sized by a count (wave 4K) -- "Add X mana of any one color, where X is the number of enchantments you control."
# (Sanctum Weaver): counted as the ability resolves (605.3a: at once), like "Add {G} for each …"
_X_COUNT = re.compile(r"^Add X mana of any one color, where X is the number of (?P<what>creatures|artifacts|enchantments|lands) "
                      r"you control$")
_URZA = re.compile(r"^If you control an? (?P<what>[A-Z][\w'-]*(?: [A-Z][\w'-]*)*(?: and an? [A-Z][\w'-]*(?: [A-Z][\w'-]*)*)*), "
                   r"add (?P<add>(?:\{[WUBRGC]\})+) instead$")  # (wave 3R3: the Urza lands)
# -- this-turn history (wave 4D) -- "If you played a land this turn, add {B} instead." (River of Tears; 305.1, 701.18a:
# played, not put onto the battlefield): ``instead_if`` holds this marker instead of permanents to control
_PLAYED_LAND = re.compile(r"^If you played a land this turn, add (?P<add>(?:\{[WUBRGC]\})+) instead$")
PLAYED_LAND = ("@played_land",)
# -- kicked / instead (wave 4G) -- "If you control four or more creatures, add {G}{G} instead." (Leafkin Druid); "If you
# control a creature with power 4 or greater, add two mana of any one color instead." (Ilysian Caryatid). 605.3a: a mana
# ability resolves as it's activated, so the condition is checked then (608.2c: the "instead" replaces the first "Add").
# ``instead_if`` holds one marker: ("@count", <card type>, n) or ("@power", n) — creatures with that power or more.
_CONTROL_INSTEAD = re.compile(rf"^If you control (?:{_N} or more (?P<what>creatures|artifacts|enchantments|lands)|"
                              r"a creature with power (?P<p>\d+) or greater), (?P<add>add .+) instead$")
_CHOSEN_COLOR: dict[str, str | None] = {  # (wave 3R3) "Choose a color. <this>": how many of that color
    "Add one mana of that color": None,
    "Add an amount of mana of that color equal to your devotion to that color": "devotion",  # 700.5 (Nykthos)
    "Add one mana of that color for each charge counter on this artifact": "counters:charge",  # (Astral Cornucopia)
    "Add an amount of mana of that color equal to the number of creatures you control of the chosen type": "chosen_type",
}
_PUT_SELF = re.compile(r"^Put an? (?P<k>[+-]\d+/[+-]\d+) counter on (?:this \w+|~)$")  # (wave 3R3: Wall of Roots)
_SAC_SELF = re.compile(r"^Sacrifice (this \w+|it)$")
_EXTRA = re.compile(r"^(\{[^}]+\})+$|^Pay \d+ life$|^Pay (?:\{E\})+$|^Pay (?:one|two|three|four|five|six|seven|eight) \{E\}$|^Remove (a|an|one|two|three) [a-z]+ counters? from (this \w+|it)$")


# -- ability words (wave 4F) ---------------------------------------------------------------------------
# "Metalcraft — {T}: Add one mana of any color. Activate only if you control three or more artifacts." (Mox
# Opal): the ability word has no rules meaning (207.2c), so the line is read without it; a flavor word the
# same (207.2d; oracle.word_prefix: never a keyword written "Name —" such as exhaust, 702.177). Any other
# "Activate only if [condition]" the condition grammar reads (app/rules/conditions.py) is kept as
# ``"cond:<json>"`` and checked as the ability would be activated (602.5: a mana ability too, 605.3a).
_ACTIVATE_IF = re.compile(r"^Activate only if (?P<cond>.+)$")


def _without_ability_word(text: str) -> str:
    from app.rules.oracle import word_prefix

    worded = word_prefix(text)
    return worded[1] if worded is not None else text


def _general_condition(text: str) -> str | None:
    import json

    from app.rules import conditions

    cond = conditions.parse(text)
    if cond is None or conditions.is_cast_condition(cond):
        return None
    return "cond:" + json.dumps(cond, sort_keys=True)
# -- end ability words (wave 4F) --


def _choice_part(part: str) -> bool:
    """-- refused copy/mana (wave 3R3) -- a cost part the payer pays with objects they choose (601.2h via
    602.2b): sacrificing, discarding, tapping an untapped permanent, exiling from the graveyard."""
    from app.rules import costs as C

    found = C.parse_ability_cost(part, card_name="~")
    return not found.unsupported and not found.activation_only and bool(found.components) and all(  # (activation_only: wave 4H)
        c.selector is not None and c.kind in (C.SACRIFICE, C.DISCARD, C.TAP_OTHER, C.EXILE_FROM_GRAVEYARD) and not c.random
        for c in found.components)


def parse_mana_ability(text: str, identity: tuple[str, ...] = COLORS) -> ManaAbility | None:
    """Understand a mana ability. ``identity`` is the controller's commander color identity (for
    Command Tower-style wording). Returns None for wordings the engine doesn't carry out."""
    text = _without_ability_word(text.strip())  # -- ability words (wave 4F) --
    text = _mana_riders.normalise(text)  # -- mana riders (wave 5A) -- "For each color among …, add …"
    m = _COST_AND_EFFECT.match(text)
    if not m:
        return None
    cost = [c.strip() for c in m.group("cost").split(",")]
    tap = "{T}" in cost
    sacrifice = False
    chooses = False
    self_counter: str | None = None
    extra: list[str] = []
    for part in cost:
        if part in ("{T}", "{0}"):
            continue
        if _SAC_SELF.fullmatch(part):
            sacrifice = True
        elif _EXTRA.fullmatch(part) and part not in ("{Q}", "{E}", "{S}"):
            extra.append(part)
        elif _choice_part(part):  # -- refused copy/mana (wave 3R3) --
            extra.append(part)
            chooses = True
        elif (pc := _PUT_SELF.fullmatch(part)) and self_counter is None:  # -- refused copy/mana (wave 3R3) --
            self_counter = pc.group("k")
        else:
            return None  # e.g. energy, exiling the source: by hand for now
    sentences = [x.strip() for x in re.split(r"(?<=\.)\s+", m.group("effect").strip()) if x.strip()]
    count: str | None = None
    # -- refused copy/mana (wave 3R3) -- "Choose a color. Add …" (106.1: the color is chosen as the ability
    # resolves; 605.3a: at once): one option per color, its amount counted for that color
    chosen_color = sentences[0] == "Choose a color."
    if chosen_color:
        sentences = sentences[1:]
        if not sentences:
            return None
    first = sentences[0].rstrip(".")
    options: tuple[tuple[str, ...], ...] | None
    if chosen_color:
        if first not in _CHOSEN_COLOR:
            return None
        count, options = _CHOSEN_COLOR[first], tuple((col,) for col in COLORS)
    elif c := _FOR_EACH.fullmatch(first):
        what = c.group("what")
        count = f"control:{_COUNT_TYPES.get(what, what)}"
        options = ((c.group("sym"),),)
    elif c := _COUNTERS_FOR_EACH.fullmatch(first):
        count, options = f"counters:{c.group('kind')}", ((c.group("sym"),),)
    elif c := _POWER_OF.fullmatch(first):
        count, options = "power", ((c.group("sym"),),)
    elif _X_POWER.fullmatch(first):
        count, options = "power", tuple((col,) for col in COLORS)
    elif c := _X_COUNT.fullmatch(first):  # (wave 4K)
        count, options = f"control:{_COUNT_TYPES[c.group('what')[:-1]]}", tuple((col,) for col in COLORS)
    elif (more_forms := _mana_riders.first_sentence(first)) is not None:  # -- mana riders (wave 5A) --
        count, options = more_forms
    else:
        options = _effect_options(sentences[0], identity)
    if options is None:
        return None
    riders: list[tuple[str, int]] = []
    spend_only: str | None = None
    instead_if: tuple[tuple[str, ...], ...] = ()
    instead: tuple[tuple[str, ...], ...] = ()
    once = False
    condition: str | None = None
    for sentence in sentences[1:]:
        s = sentence.rstrip(".")
        if d := _DAMAGE_YOU.fullmatch(s):
            riders.append(("damage", int(d.group("n"))))
        elif s == "Draw a card":
            riders.append(("draw", 1))
        elif (rd := _mana_riders.rider(s)) is not None:  # -- mana riders (wave 5A) -- "You gain 2 life."
            riders.append(rd)
        elif s == "Activate only once each turn":
            once = True
        elif c := _CONTROL.fullmatch(s):
            condition = f"control:{c.group('what')}" + (f"|{c.group('or')}" if c.group("or") else "")
        elif c := _CONTROL_COUNT.fullmatch(s):
            condition = f"count:{_COUNT_TYPES[c.group('what').rstrip('s')]}:{_NUM[c.group(1)]}"
        elif (g := _ACTIVATE_IF.fullmatch(s)) and condition is None:  # -- ability words (wave 4F) --
            general = _general_condition(g["cond"])
            if general is None:
                return None
            condition = general
        elif (u := _URZA.fullmatch(s)) and not instead and len(options) == 1:  # -- refused copy/mana (wave 3R3) --
            needs = tuple(tuple(x.split()) for x in re.split(r" and an? ", u.group("what")))
            more = _effect_options("Add " + u.group("add"), identity)
            if more is None or len(more) != 1 or not all(needs):
                return None
            instead_if, instead = needs, more
        elif (ci := _CONTROL_INSTEAD.fullmatch(s)) and not instead and count is None:  # -- kicked / instead (wave 4G) --
            more = _effect_options("A" + ci.group("add")[1:], identity)
            if more is None or not all(more) or any(x not in ALL_MANA for opt in (*options, *more) for x in opt):
                return None  # (plain mana only: no chosen color, no "a land could produce")
            marker = ("@power", ci.group("p")) if ci.group("p") else \
                ("@count", _COUNT_TYPES[ci.group("what").rstrip("s")], str(_NUM[ci.group(1)]))
            instead_if, instead = (marker,), more
        elif (pl := _PLAYED_LAND.fullmatch(s)) and not instead and len(options) == 1:  # -- this-turn history (wave 4D) --
            more = _effect_options("Add " + pl.group("add"), identity)
            if more is None or len(more) != 1:
                return None
            instead_if, instead = (PLAYED_LAND,), more
        else:
            for pattern, kind in _SPEND:
                if sm := pattern.fullmatch(s):
                    spend_only = f"type:{sm.group('t')}" if kind == "type" else kind
                    break
            else:
                q = parse_spend(s)  # -- refused copy/mana (wave 3R3): the general restriction grammar --
                if q is None or spend_only is not None:
                    return None  # a rider the engine doesn't know: leave the ability manual
                spend_only = q
    return ManaAbility(tap=tap, sacrifice_self=sacrifice, options=options, extra_cost=", ".join(extra),
                       riders=tuple(riders), spend_only=spend_only, once_per_turn=once, condition=condition,
                       count=count, chooses=chooses, instead_if=instead_if, instead=instead, self_counter=self_counter)


@dataclass(frozen=True)
class Source:
    card_id: str
    options: tuple[tuple[str, ...], ...]
    sacrifice: bool = False
    rank: int = 0  # tie-breaker: lower is tapped first (lands before creatures, …)
    preferred: bool = False  # the player marked it PREFER: used before anything else that fits
    # Parallel to ``options``: which of the permanent's abilities gives it (for riders and costs).
    abilities: tuple[int, ...] = ()
    activation: ManaCost | None = None  # a mana cost to activate (a filter), paid by other sources

    @property
    def flexibility(self) -> int:
        return len({m for opt in self.options for m in opt})


@dataclass
class Payment:
    tapped: list[str] = field(default_factory=list)
    sacrificed: list[str] = field(default_factory=list)
    produced: dict[str, int] = field(default_factory=dict)  # mana added by the tapped sources
    spent: dict[str, int] = field(default_factory=dict)  # mana taken from the pool (after producing)
    life: int = 0  # life paid for Phyrexian symbols
    used: list[tuple[str, int]] = field(default_factory=list)  # (source card, ability index) per tapped source

    def delta(self) -> dict[str, int]:
        out = dict(self.produced)
        for k, v in self.spent.items():
            out[k] = out.get(k, 0) - v
        return {k: v for k, v in out.items() if v}


MAX_SEARCH = 20000
Chosen = list[tuple[Source, tuple[str, ...]]]
Found = tuple[dict[str, int], Chosen]


def _solve(reqs: list[tuple[str, ...]], generic: int, pool: dict[str, int], sources: list[Source]
           ) -> tuple[dict[str, int], list[tuple[Source, tuple[str, ...]]]] | None:
    """DFS over coloured/hybrid requirements; generic mana is paid last from whatever is left.
    Returns (units left over after paying, sources tapped with the option used)."""
    budget = [MAX_SEARCH]

    def generic_from(units: dict[str, int], remaining: list[Source], n: int, chosen: Chosen) -> Found | None:
        units = dict(units)
        # tap the sources that give the most mana first (Sol Ring before a Forest)
        for src in sorted(remaining, key=lambda s: (not s.preferred, -max(len(o) for o in s.options), s.flexibility, s.rank)):
            if sum(units.values()) >= n:
                break
            opt = max(src.options, key=len)
            for m in opt:
                units[m] = units.get(m, 0) + 1
            chosen = [*chosen, (src, opt)]
        if sum(units.values()) < n:
            return None
        for _ in range(n):  # spend colourless first, then the most plentiful colour
            k = max((c for c in units if units[c] > 0), key=lambda c: (c == "C", units[c]))
            units[k] -= 1
        return {k: v for k, v in units.items() if v}, chosen

    def dfs(i: int, units: dict[str, int], remaining: list[Source], chosen: Chosen, extra_generic: int) -> Found | None:
        budget[0] -= 1
        if budget[0] < 0:
            return None
        if i == len(reqs):
            return generic_from(units, remaining, generic + extra_generic, chosen)
        req = reqs[i]
        if req[0].isdigit():  # {2/B}: {B}, or two generic
            alt = _pay_one(units, remaining, chosen, (req[1],))
            for u2, rem2, ch2 in alt:
                r = dfs(i + 1, u2, rem2, ch2, extra_generic)
                if r:
                    return r
            return dfs(i + 1, units, remaining, chosen, extra_generic + int(req[0]))
        for u2, rem2, ch2 in _pay_one(units, remaining, chosen, req):
            r = dfs(i + 1, u2, rem2, ch2, extra_generic)
            if r:
                return r
        return None

    return dfs(0, {k: v for k, v in pool.items() if v > 0}, sources, [], 0)


def _pay_one(units: dict[str, int], remaining: list[Source], chosen: Chosen, req: tuple[str, ...]
             ) -> Iterator[tuple[dict[str, int], list[Source], Chosen]]:
    """Ways to pay one symbol that accepts any colour in ``req``: from the pool, else by tapping a source."""
    for color in req:
        if units.get(color, 0) > 0:
            new = dict(units)
            new[color] -= 1
            yield new, remaining, chosen
    for j, src in enumerate(remaining):
        for opt in src.options:
            wanted = next((c for c in req if c in opt), None)
            if wanted is None:
                continue
            new = dict(units)
            for m in opt:
                new[m] = new.get(m, 0) + 1
            new[wanted] -= 1
            yield new, remaining[:j] + remaining[j + 1:], [*chosen, (src, opt)]


def solve(cost: ManaCost, pool: dict[str, int], sources: list[Source], *, life: int = 0) -> Payment:
    """Find a payment for ``cost`` (X already fixed). Raises ManaError if there is none."""
    if cost.unsupported:
        raise ManaError(f"Can't pay {' '.join('{' + s + '}' for s in cost.unsupported)} automatically")
    ordered = sorted(sources, key=lambda s: (not s.preferred, s.flexibility, s.rank, -max(len(o) for o in s.options)))
    base = [(c,) for c in cost.colored] + sorted(cost.hybrid, key=len)
    attempts = [(base + [(c,) for c in cost.phyrexian], 0)]  # Phyrexian with mana first …
    if cost.phyrexian:
        attempts.append((base, 2 * len(cost.phyrexian)))  # … else with 2 life each
    for reqs, life_cost in attempts:
        if life_cost and life_cost >= life:
            continue
        found = _solve(reqs, cost.generic, pool, ordered)
        if found is None:
            continue
        left, chosen = found
        payment = Payment(life=life_cost)
        for src, opt in chosen:
            payment.tapped.append(src.card_id)
            if src.sacrifice:
                payment.sacrificed.append(src.card_id)
            if src.abilities:
                payment.used.append((src.card_id, src.abilities[src.options.index(opt)]))
            for m in opt:
                payment.produced[m] = payment.produced.get(m, 0) + 1
        total = {k: v for k, v in pool.items() if v > 0}
        for k, v in payment.produced.items():
            total[k] = total.get(k, 0) + v
        payment.spent = {k: v - left.get(k, 0) for k, v in total.items() if v - left.get(k, 0) > 0}
        return payment
    raise ManaError(f"Not enough mana to pay {cost.text()}")


def symbols(mana: dict[str, int]) -> str:
    """{"G": 2, "C": 1} → "{C}{G}{G}"."""
    return "".join(f"{{{c}}}" * mana.get(c, 0) for c in ALL_MANA) or "{0}"


# -- refused copy/mana (wave 3R3) -----------------------------------------------------------------------
# 106.6: "Spend this mana only to cast <spells> [or activate abilities of <sources>]" in general: the
# restriction as a closed description ("q:" + JSON, read by ``casting.spend_allowed``). Each side is
# None (not allowed), "any" or alternatives; one alternative is {types, subtypes, supertypes, color,
# non} that must all hold ("a Chandra planeswalker spell": the subtype Chandra and the type
# Planeswalker). "of the chosen type" is the creature type chosen as the source entered ("chosen":
# resolved by ``casting.mana_abilities`` from the permanent's choice; no choice: it can't be used).
# Refused (the ability stays manual): riders ("and that spell can't be countered", 106.6a), costs
# rather than spells ("pay cumulative upkeep costs", "costs that contain {X}", "turn … face up",
# "unlock a door", "foretell"), spells described by where they're cast from, by keywords, by mana
# value or by "you don't own" — the payer can't check those here. A restriction on mana a spell or a
# triggered ability adds (Geosurge, Sarkhan, Fireblood; Klauth and Karn, Legacy Reforged with kept mana) stays
# manual: the pool is one count per type and carries no restriction. Mana Drain stays manual: its delayed
# "at the beginning of your next main phase" reads the countered spell's mana value as it last existed on
# the stack (X included), which the countered card in the graveyard no longer shows.
_CARD_TYPES = {"artifact": "Artifact", "creature": "Creature", "enchantment": "Enchantment", "instant": "Instant",
               "sorcery": "Sorcery", "planeswalker": "Planeswalker", "land": "Land", "battle": "Battle", "kindred": "Kindred"}
_SUPERTYPES = {"legendary": "Legendary", "snow": "Snow"}


def _known_subtype(word: str) -> bool:
    from app.rules.creature_types import CREATURE_TYPES
    from app.rules.layers import ARTIFACT_TYPES, BATTLE_TYPES, ENCHANTMENT_TYPES, LAND_TYPES, SPELL_TYPES

    return word in CREATURE_TYPES or word in ARTIFACT_TYPES or word in ENCHANTMENT_TYPES or word in LAND_TYPES \
        or word in SPELL_TYPES or word in BATTLE_TYPES


def _plural(word: str) -> str:
    return word[:-1] if word.endswith("s") and not word.endswith("ss") else word


def _alt(words: str, *, source: bool) -> dict[str, object] | None:
    """One alternative ("instant", "Vampire", "legendary creature", "colorless", "Chandra planeswalker",
    "creature … of the chosen type"); ``source``: the words name a permanent ("creatures", "Elementals")."""
    out: dict[str, object] = {}
    text = words.strip()
    if text.endswith(" of the chosen type"):
        out["chosen"] = True
        text = text[: -len(" of the chosen type")]
    tokens = text.split()
    types: list[str] = []
    subs: list[str] = []
    supers: list[str] = []
    i = 0
    while i < len(tokens):
        w = tokens[i]
        bare = _plural(w) if source else w
        two = " ".join(tokens[i:i + 2])
        if i + 1 < len(tokens) and (_known_subtype(two) or (source and _known_subtype(_plural(two)))):  # ("Time Lord")
            subs.append(two if _known_subtype(two) else _plural(two))
            i += 2
            continue
        if w.lower() in _CARD_TYPES or bare.lower() in _CARD_TYPES:
            types.append(_CARD_TYPES[w.lower() if w.lower() in _CARD_TYPES else bare.lower()])
        elif w in _SUPERTYPES:
            supers.append(_SUPERTYPES[w])
        elif w in ("colorless", "multicolored", "monocolored"):
            out["color"] = w
        elif w in ("noncreature", "nonartifact"):
            out["non"] = [_CARD_TYPES[w[3:]]]
        elif w[:1].isupper() and (_known_subtype(w) or _known_subtype(bare)):
            subs.append(w if _known_subtype(w) else bare)
        elif w[:1].isupper() and i + 1 < len(tokens) and tokens[i + 1] == "planeswalker":
            subs.append(w)  # (a planeswalker type: "a Chandra planeswalker spell", 205.3j)
        elif w in ("source", "sources", "permanent", "permanents") and source:
            pass
        else:
            return None
        i += 1
    if not (types or subs or supers or "color" in out or "non" in out):
        return None
    if out.get("chosen") and types != ["Creature"]:
        return None
    if types:
        out["types"] = types
    if subs:
        out["subtypes"] = subs
    if supers:
        out["supertypes"] = supers
    return out


def _alts(phrase: str, *, source: bool) -> list[dict[str, object]] | None:
    p = re.sub(r"^(?:an?|one or more) ", "", phrase.strip())
    parts = [x for x in re.split(r",? and/or |,? or |, and |, | and ", p) if x]
    out = []
    for part in parts:
        part = re.sub(r"^(?:an?) ", "", part)
        if not source:  # ("instant and sorcery spells": the noun may come once, at the end)
            part = re.sub(r" spells?(?= of the chosen type$)| spells?$", "", part)
        alt = _alt(part, source=source)
        if alt is None:
            return None
        out.append(alt)
    if any(a.get("chosen") for a in out) and len(out) > 1:
        return None
    return out or None


_GENERIC_SPEND = re.compile(
    r"^Spend this mana only to (?:(?P<cast>cast (?P<spells>.+?))(?: (?:or|and) (?:to )?(?P<act>activate (?:an ability|abilities)"
    r"(?: of (?P<src>.+))?))?|(?P<act2>activate (?:an ability|abilities)(?: of (?P<src2>.+?))?)(?: or (?:to )?cast (?P<spells2>.+))?)$")


def parse_spend(sentence: str) -> str | None:
    """A general "Spend this mana only to …" restriction as "q:<json>" (None: not one the payer checks)."""
    import json

    s = sentence.strip().rstrip(".")
    if s == "This mana can't be spent to cast spells":
        return "q:" + json.dumps({"cast": None, "ability": "any"}, sort_keys=True)
    m = _GENERIC_SPEND.fullmatch(s)
    if m is None:
        return None
    spells = m["spells"] if m["cast"] else m["spells2"]
    acts = bool(m["act"] or m["act2"])
    src = m["src"] if m["cast"] else m["src2"]
    spec: dict[str, object] = {"cast": None, "ability": None}
    if spells is not None:
        if spells in ("spells", "a spell"):
            spec["cast"] = "any"
        else:
            alts = _alts(spells, source=False)
            if alts is None:
                return None
            spec["cast"] = alts
    if acts:
        if src is None:
            spec["ability"] = "any"
        else:
            alts = _alts(src, source=True)
            if alts is None:
                return None
            spec["ability"] = alts
    return "q:" + json.dumps(spec, sort_keys=True)


def spend_alt_matches(alt: dict[str, Any], ch: Any) -> bool:
    """Does one alternative of a "q:" restriction hold for these characteristics?"""
    types: frozenset[str] = ch.types
    colors: frozenset[str] = ch.colors
    if any(t not in types for t in alt.get("types") or []):
        return False
    if any(t not in ch.subtypes for t in alt.get("subtypes") or []):
        return False
    if any(t not in ch.supertypes for t in alt.get("supertypes") or []):
        return False
    if any(t in types for t in alt.get("non") or []):
        return False
    color = alt.get("color")
    if color == "colorless" and colors:
        return False
    if color == "multicolored" and len(colors) < 2:
        return False
    return not (color == "monocolored" and len(colors) != 1)
# -- end refused copy/mana (wave 3R3) --
