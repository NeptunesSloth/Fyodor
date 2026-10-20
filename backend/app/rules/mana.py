"""Mana: costs, mana abilities, and paying for things.

* ``parse_cost("{2}{G}{G}")`` → a ``ManaCost``.
* ``parse_mana_ability("{T}: Add {R} or {G}.")`` → what a mana ability produces, or ``None`` when
  the wording isn't one the engine understands (the ability then stays a manual one).
* ``solve(cost, pool, sources)`` finds a way to pay: mana already in the pool first, then untapped
  sources, preferring the least flexible ones so dual lands and "any color" sources are kept for
  last (roughly what Arena's auto-payment does).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from itertools import combinations_with_replacement
from typing import Any

from app.rules.mana_requirement_rows import OutputProducer, ProducerFact, RequirementPlan, SpentClass
from app.rules.mana_requirement_rows import ProducerRequirement as ProducerRequirement

# isort: split
# Requirement identities must exist before cyclic rule consumers build adapters.
from app.rules import costs as _costs
from app.rules import mana_riders as _mana_riders  # -- mana riders (wave 5A) --
from app.rules import mana_units as _mana_units  # -- mana provenance (wave 18B) --
from app.rules import removed_mana as _removed_mana  # -- if you do (wave 6F) --

COLORS = ("W", "U", "B", "R", "G")
ALL_MANA = (*COLORS, "C")
# -- snow mana (wave 7E) -- 107.4h: {S} is paid with one mana of any type produced by a snow source (106.3 / 205.4g: a snow
# permanent). The pool is one plain count per type and doesn't record where its mana came from, so {S} is paid only by
# tapping a snow source as the cost is paid (``Source.snow``); mana already in the pool never pays it.
SNOW = "S"
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
    allocation: RequirementPlan | None = None  # Internal requirement origin before payment-only encodings.

    def with_x(self, x: int) -> ManaCost:
        return ManaCost(self.generic + x * self.x, self.colored, self.hybrid, self.phyrexian, 0, self.unsupported,
                        replace(self.allocation, generic=self.allocation.generic + x * self.x) if self.allocation else None)

    def plus_generic(self, n: int) -> ManaCost:
        return ManaCost(self.generic + n, self.colored, self.hybrid, self.phyrexian, self.x, self.unsupported,
                        replace(self.allocation, generic=max(0, self.allocation.generic + n)) if self.allocation else None)

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


# Internal cost choice after an as-though permission: any mana type, or two life.
# This exact sentinel is not a new family of printed Phyrexian symbols.
ANY_PHYREXIAN = "W/U/B/R/G/C"


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
        elif sym in ALL_MANA or sym == SNOW:  # -- snow mana (wave 7E) -- {S} is a colored requirement of its own (107.4h)
            colored.append(sym)
        elif sym.endswith("/P") and (sym[:-2] == ANY_PHYREXIAN or all(c in COLORS for c in sym[:-2].split("/"))):
            phyrexian.append(sym[:-2])  # (-- review 38 -- 107.4f: a hybrid Phyrexian {G/W/P} is kept whole, "G/W": {G}, {W} or 2 life)
        elif "/" in sym:
            hybrid.append(tuple(sym.split("/")))
        else:
            unsupported.append(sym)
    return ManaCost(generic, tuple(colored), tuple(hybrid), tuple(phyrexian), x, tuple(unsupported))


# -- as long as (wave 9B) -- 118.14 / 609.4b: "mana of any type can be spent" and "spend mana as though it were mana of any
# color" change only how the cost may be paid. Any type: every symbol made of mana types is paid by one mana of any type
# (a generic requirement; {S} still needs a snow source, a Phyrexian symbol keeps its own way: the choice is only wider
# there). Any color: a colored or all-color hybrid symbol is paid by one mana of any kind (colorless mana is treated as the color,
# wave 22F); {C} and {2/B}-style symbols are untouched. (Any type: {2/B} becomes one generic.)
def spend_as(cost: ManaCost, mode: str) -> ManaCost:
    from app.rules import mana_allocation_masks

    transformed = _spend_as(cost, mode)
    if mode not in ('type', 'color', 'colorless_color'):
        return transformed
    return replace(transformed, allocation=mana_allocation_masks.requirements(cost, mode))


def _spend_as(cost: ManaCost, mode: str) -> ManaCost:
    if mode == 'colorless_color':
        # Only actual C may substitute for a colored requirement. Allocation and
        # provenance retain the actual mana type, including restricted units.
        return ManaCost(cost.generic, tuple(c for c in cost.colored if c not in COLORS),
                        tuple((c, 'C') for c in cost.colored if c in COLORS) +
                        tuple(tuple(dict.fromkeys((*h, 'C'))) if any(c in COLORS for c in h) else h for h in cost.hybrid),
                        tuple('/'.join(dict.fromkeys((*c.split('/'), 'C'))) if any(k in COLORS for k in c.split('/')) else c
                              for c in cost.phyrexian), cost.x, cost.unsupported)
    if mode == "type":
        return ManaCost(cost.generic + sum(1 for c in cost.colored if c != SNOW) + len(cost.hybrid),  # ({2/B}: one mana pays {B})
                        tuple(c for c in cost.colored if c == SNOW), (), (ANY_PHYREXIAN,) * len(cost.phyrexian), cost.x, cost.unsupported)
    if mode == "color":
        # -- casting costs (wave 22F) -- 609.4: colorless mana spent "as though it were mana of any color" is treated as the color
        # needed, so a colored (or all-color hybrid) symbol is paid by any one mana; {C} and {2/B}-style symbols are untouched
        paid = sum(1 for c in cost.colored if c in COLORS) + sum(1 for h in cost.hybrid if all(x in COLORS for x in h))
        return ManaCost(cost.generic + paid, tuple(c for c in cost.colored if c not in COLORS),
                        tuple(h for h in cost.hybrid if not all(x in COLORS for x in h)),
                        (ANY_PHYREXIAN,) * len(cost.phyrexian), cost.x, cost.unsupported)
    return cost


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
    reveal_hand: str | None = None  # private optional effect choice; never an automatic source
    borrowed_link_scope: str | None = None  # separately acquired607.5 exile link; never the donor's record
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
    # -- mana riders (wave 5A) -- "Exile this card from your hand: Add {R}." (Simian Spirit Guide): activated only
    # from its owner's hand (113.6m, 605.3a), by hand only (app/rules/mana_riders.activate_from_hand)
    from_hand: bool = False
    # -- mana provenance (wave 18B) -- "When that mana is spent to cast …, …" / "If that mana is spent on …, that spell can't be
    # countered": the riders (JSON dicts, mana_units.RIDERS) the mana it adds carries (106.6)
    on_spend: tuple[str, ...] = ()
    spend_text: str = ""  # the restriction sentence, for the pool display
    delayed_effects: tuple[dict[str, Any], ...] = ()  # Native delayed effects created as this mana ability resolves.
    immediate_effects: tuple[dict[str, Any], ...] = ()  # Native nonstack resolution, with persistent terminal.
    from_graveyard: bool = False
    native_body: bool = False
    output_producers: tuple[tuple[OutputProducer | None, ...], ...] | None = None
    generic_allowed: bool = True  # CR106.6: eligibility of actual produced units for generic requirements.

    def __post_init__(self) -> None:
        if self.output_producers and (len(self.output_producers) != len(self.options)
                or any(len(profile) != len(option) for profile, option in zip(self.output_producers, self.options, strict=True))):
            raise ValueError('Every mana output position needs its own producer entry')

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
    if effect in ("Add one mana of any of this creature's colors", "Add one mana of any of ~'s colors", "Add one mana of any of its colors"):  # -- counters (wave 44C) -- Katilda, Dawnhart Prime (read in casting.mana_abilities)
        return (("OWN_COLORS",),)
    if effect in ("Add one mana of any of the exiled card's colors", "Add one mana of any of the exiled cards' colors"):  # -- imprint (wave 51B) -- Chrome Mox, Pit of Offerings: the colors of what the linked exile ability put there (607.2a; casting._resolve_options)
        return (("EXILED_COLORS",),)
    # -- mana (wave 19E) -- "any color that a land / basic land / Gate you control could produce", "any type that a Gate …":
    # ("LANDS:<color|type>:<land|basic|Gate>",) read by casting.mana_abilities
    if m := re.fullmatch(r"Add one mana of any (?P<k>color|type) that an? (?P<f>land|basic land|Gate) you control could produce", effect):
        return ((f"LANDS:{m['k']}:{m['f'].split()[0]}",),)
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
    (re.compile(r"^Spend this mana only to cast an instant or sorcery spell or to gain a Class level$"), "instant_sorcery_or_class_level"),
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
_POWER_OF = re.compile(r"^Add an amount of \{(?P<sym>[WUBRGC])\} equal to (?:this creature|[A-Z][^.]{0,60}?)'s (?P<stat>power|toughness)$")  # (toughness: wave 17B, Vhal)
# -- activated sweep (wave 17B) -- "{T}, Sacrifice an artifact: Add an amount of {B} equal to the sacrificed artifact's mana value."
# (Priest of Yawgmoth): the mana value of what the cost sacrificed, as it was (608.2h; casting._activate_choosing)
_SAC_MV = re.compile(r"^Add an amount of \{(?P<sym>[WUBRGC])\} equal to the sacrificed (?:creature|artifact|permanent|land|enchantment)'s mana value$")
_X_POWER = re.compile(r"^Add X mana of any one color, where X is (?:this creature|[A-Z][^.]{0,60}?)'s power$")
# -- X sized by a count (wave 4K) -- "Add X mana of any one color, where X is the number of enchantments you control."
# (Sanctum Weaver): counted as the ability resolves (605.3a: at once), like "Add {G} for each …"
_X_COUNT = re.compile(r"^Add X mana of any one color, where X is the number of (?P<what>creatures|artifacts|enchantments|lands) "
                      r"you control$")
_URZA = re.compile(r"^If you control an? (?P<what>[A-Z][\w'-]*(?: [A-Z][\w'-]*)*(?: and an? [A-Z][\w'-]*(?: [A-Z][\w'-]*)*)*), "
                   r"add (?P<add>(?:\{[WUBRGC]\})+) instead$")  # (wave 3R3: the Urza lands)
# -- named permanents (wave 35C) -- "If you control creatures named Mine Worker and Power Plant Worker, add {C}{C}{C} instead." (Tower Worker): a
# creature with each name (the ruling: at least one of each); ``instead_if`` holds ("@named", <name>) for each
_NAMED_INSTEAD = re.compile(r"^If you control creatures named (?P<a>[A-Z][\w'-]*(?: [A-Z][\w'-]*)*) and (?P<b>[A-Z][\w'-]*(?: [A-Z][\w'-]*)*), "
                            r"add (?P<add>(?:\{[WUBRGC]\})+) instead$")
# -- this-turn history (wave 4D) -- "If you played a land this turn, add {B} instead." (River of Tears; 305.1, 701.18a:
# played, not put onto the battlefield): ``instead_if`` holds this marker instead of permanents to control
_PLAYED_LAND = re.compile(r"^If you played a land this turn, add (?P<add>(?:\{[WUBRGC]\})+) instead$")
PLAYED_LAND = ("@played_land",)
# -- designations (wave 45B) -- "If you have the initiative, add {C}{C} instead." (Sarevok's Tome), "If you've completed a dungeon, add six {G} instead."
# (Undermountain Adventurer; 726.1, 309.7): checked as the ability resolves (605.3a); ``instead_if`` holds ("@status", <the designation>)
_STATUS_INSTEAD = re.compile(r"^If you(?: have the (?P<i>initiative)|'ve completed a (?P<d>dungeon)), (?P<add>add .+) instead$")
# -- opening hand (wave 18C) -- "If Gemstone Caverns has a luck counter on it, instead add one mana of any color." (122.1: the
# source's own counters, checked as the ability resolves, 605.3a): ``instead_if`` holds ("@counter", <kind>)
# -- most-played cards (wave 51F) -- "If this creature has a +1/+1 counter on it, add three mana of that type instead." (Incubation Druid, 605.3a): the type picked for the
# first sentence, three times; ``instead_if`` holds ("@counter", <kind>) and ``instead`` ("LANDS", "LANDS", "LANDS") (casting._resolve_options)
_OWN_COUNTER_TRIPLE = re.compile(r"^If (?:~|this [a-z]+) has an? (?P<k>\+1/\+1) counter on it, add three mana of that type instead$")
_OWN_COUNTER_INSTEAD = re.compile(r"^If (?:~|this [a-z]+|[A-Z][\w',-]*(?: (?:of |the |[A-Z])[\w',-]*)*) has an? (?P<k>[a-z]+) counter on "
                                  r"it, instead (?P<add>add .+)$")
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
_SAC_SELF = re.compile(r"^Sacrifice (this \w+|it|~)$")  # (wave 17C: ~, a quoted grant read through self_text)
_EXTRA = re.compile(r"^(\{[^}]+\})+$|^Pay \d+ life$|^Pay (?:\{E\})+$|^Pay (?:one|two|three|four|five|six|seven|eight) \{E\}$|^Remove (a|an|one|two|three|four|five) (?:[a-z]+|[+-]\d+/[+-]\d+) counters? from (this \w+|it|~|[A-Z][\w',-]+(?: [A-Za-z',-]+)*)$")  # (wave 47D: five, the card's own name: Ramos)


# -- ability words (wave 4F) ---------------------------------------------------------------------------
# "Metalcraft — {T}: Add one mana of any color. Activate only if you control three or more artifacts." (Mox
# Opal): the ability word has no rules meaning (207.2c), so the line is read without it; a flavor word the
# same (207.2d; oracle.word_prefix: never a keyword written "Name —" such as exhaust, 702.177). Any other
# "Activate only if [condition]" the condition grammar reads (app/rules/conditions.py) is kept as
# ``"cond:<json>"`` and checked as the ability would be activated (602.5: a mana ability too, 605.3a).
_ACTIVATE_IF = re.compile(r"^Activate only if (?P<cond>.+)$")
_ACTIVATE_TURN = re.compile(r"^Activate only during (?P<w>your turn|an opponent's turn)(?P<once> and only once each turn)?$")


def _without_ability_word(text: str) -> str:
    from app.rules.oracle import word_prefix

    worded = word_prefix(text)
    return worded[1] if worded is not None else text


def _general_condition(text: str) -> str | None:
    import json

    from app.rules import (
        activation_words,  # -- activation wordings (wave 7B) --
        conditions,
    )

    cond = conditions.parse(text) or activation_words.condition(
        re.sub(r"\bthis (?:creature|land|permanent|artifact|enchantment)\b", "~", text))
    if cond is None or conditions.is_cast_condition(cond):
        return None
    return "cond:" + json.dumps(cond, sort_keys=True)
# -- end ability words (wave 4F) --


def _choice_part(part: str) -> bool:
    """-- refused copy/mana (wave 3R3) -- a cost part the payer pays with objects they choose (601.2h via
    602.2b): sacrificing, discarding, tapping an untapped permanent, exiling from the graveyard."""
    from app.rules import costs as C

    found = C.parse_ability_cost(part, card_name="~", anyn=False)
    # -- activated sweep (wave 17B) -- also exerting / untapping the source ({Q}, 107.6) and foraging (701.61a): paid by hand
    return not found.unsupported and bool(found.components) and all(
        c.kind in (C.EXERT, C.UNTAP, C.FORAGE, C.DISCARD_HAND, C.COLLECT_EVIDENCE, C.RETURN_PERMANENT, "EXILE_FROM_HAND") or (  # (wave 26C: "Discard your hand", 701.9a: no choice, paid with the rest)
            (not c.activation_only or c.kind == C.EXILE or (c.x and c.kind in (C.TAP_OTHER, C.SACRIFICE))) and c.selector is not None  # (X: Hazel, "Tap X untapped tokens")
            and c.kind in (C.SACRIFICE, C.DISCARD, C.TAP_OTHER, C.EXILE_FROM_GRAVEYARD, C.EXILE) and not c.random)
        or (c.kind == C.EXILE_FROM_GRAVEYARD and c.selector is None)
        for c in found.components)


def _native_limit(text: str) -> bool:
    from app.rules import restrictions
    if text == 'Activate only once each turn':
        return False  # Retain the existing once_per_turn representation.
    parsed = restrictions.parse(text + '.') or []
    return bool(parsed) and all(x['kind'] in ('per_turn', 'sorcery') for x in parsed)


def parse_mana_ability(text: str, identity: tuple[str, ...] = COLORS, *, card_name: str = "") -> ManaAbility | None:
    """A fresh Oracle parse has a known original producer, unlike an old saved profile."""
    parsed = _parse_mana_ability(text, identity, card_name=card_name)
    return replace(parsed, output_producers=()) if parsed is not None and parsed.output_producers is None else parsed


def _parse_mana_ability(text: str, identity: tuple[str, ...] = COLORS, *, card_name: str = "") -> ManaAbility | None:
    """Understand a mana ability. ``identity`` is the controller's commander color identity (for
    Command Tower-style wording). Returns None for wordings the engine doesn't carry out."""
    from app.rules import mana_allocation_profiles

    if (allocation := mana_allocation_profiles.parse_mana(text, identity, card_name)) is not None:
        return allocation
    from app.rules import mana_codie_profiles

    if (codie := mana_codie_profiles.parse_mana(text, identity, card_name)) is not None:
        return codie
    from app.rules import mana_foundry_profiles

    if (foundry := mana_foundry_profiles.parse_mana(text, identity, card_name)) is not None:
        return foundry
    from app.rules import mana_deity_profiles

    if (deity := mana_deity_profiles.parse_mana(text, identity, card_name)) is not None:
        return deity
    from app.rules import mana_crafted_profiles

    if (crafted := mana_crafted_profiles.parse_mana(text, identity, card_name)) is not None:
        return crafted
    from app.rules import mana_linked_profiles

    if (linked := mana_linked_profiles.parse_mana(text, identity, card_name)) is not None:
        return linked
    from app.rules import mana_resolution_profiles

    if (profile := mana_resolution_profiles.parse_mana(text, identity, card_name)) is not None:
        return profile
    from app.rules import contextual_mana_outcomes
    if (contextual := contextual_mana_outcomes.parse_mana(text, identity, card_name)) is not None:
        return contextual
    from app.rules import immediate_mana_resolutions

    if (immediate := immediate_mana_resolutions.parse(text, identity, card_name)) is not None:
        return immediate
    from app.rules import reveal_mana

    if (revealed := reveal_mana.parse(text)) is not None:
        return revealed
    text = _without_ability_word(text.strip())  # -- ability words (wave 4F) --
    from app.rules import mana_delayed_effects

    delayed_effects: tuple[dict[str, Any], ...] = ()
    if (delayed_tail := mana_delayed_effects.extract(text)) is not None:
        text, delayed_effects = delayed_tail
    text = _mana_riders.normalise(text)  # -- mana riders (wave 5A) -- "For each color among …, add …"
    m = _COST_AND_EFFECT.match(text)
    if not m:
        return None
    cost = [c.strip() for c in m.group("cost").split(",")]
    tap = "{T}" in cost
    sacrifice = False
    chooses = False
    self_counter: str | None = None
    from_hand = False  # -- mana riders (wave 5A) --
    extra: list[str] = []
    removed_kind: str | None = None  # -- if you do (wave 6F) -- "Remove any number of storage counters from this land"
    for part in cost:
        if card_name:
            from app.rules.scripts import self_text

            part = self_text(part, card_name)  # CR 201.5: a named self-cost is paid by this source
        if part in ("{T}", "{0}"):
            continue
        if (rk := _removed_mana.cost_kind(part)) is not None and removed_kind is None:  # -- if you do (wave 6F) --
            removed_kind = rk
            continue
        if part == "Exile this card from your hand" and len(cost) == 1:  # -- mana riders (wave 5A) -- (113.6m)
            from_hand = True
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
    if removed_kind is not None:  # -- if you do (wave 6F) -- "Add {C} for each storage counter removed this way"
        found_removed = None if chosen_color else _removed_mana.first_sentence(first, removed_kind)
        if found_removed is None:
            return None
        count, options = found_removed
    elif any(c.x for p in extra for c in _costs.parse_ability_cost(p, card_name="~").components):
        # -- activated sweep (wave 17B) -- "Tap X untapped tokens you control: Add X mana in any combination of colors." (Hazel of
        # the Rootbloom): X is announced as the cost is paid (107.3a), the mana is X of them (casting._activate_choosing)
        mix = None if chosen_color else _removed_mana.x_mix(first)
        if mix is None:
            return None
        count, options = f"xcost:{mix[0]}:{mix[1]}", tuple((c,) for c in mix[1])
    elif chosen_color and (cc := re.fullmatch(r"Add one mana of that color for each (?P<what>.+)", first)):
        # -- activated sweep (wave 17B) -- "Choose a color. Add one mana of that color for each different power among creatures you
        # control." (Selvala, Eager Trailblazer): counted as it's activated (605.3b)
        count = _mana_riders._value(cc["what"])
        if count is None:
            return None
        options = tuple((col,) for col in COLORS)
    elif chosen_color:
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
        count, options = c.group("stat"), ((c.group("sym"),),)
    elif c := _SAC_MV.fullmatch(first):
        if not any(k.kind == _costs.SACRIFICE and k.selector is not None for p in extra for k in _costs.parse_ability_cost(p, card_name="~").components):
            return None
        count, options = "sacrificed_mv", ((c.group("sym"),),)
    elif first == "Add X mana of any one color, where X is 1 plus the exiled creature's mana value":
        if not any(k.kind == _costs.EXILE and k.selector is not None for p in extra for k in _costs.parse_ability_cost(p, card_name="~").components):
            return None
        count, options = "exiled_mv_plus_one", tuple((col,) for col in COLORS)
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
    on_spend: list[str] = []  # -- mana provenance (wave 18B) -- 106.6 riders (mana_units.rider)
    spend_text = ""
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
        elif s.startswith("Activate ") and _native_limit(s):
            pass  # Native activation preflight/enumeration reads the original restriction.
        elif s == "Activate only once each turn":
            once = True
        elif s == "Activate only as an instant" and chooses:
            pass  # -- activated sweep (wave 26C) -- 602.5d: when you have priority; a cost of objects is only ever paid by hand (never mid-payment)
        elif (t := _ACTIVATE_TURN.fullmatch(s)) and condition is None:  # -- activated sweep (wave 17B) -- 602.5d: whose turn it is
            condition = _general_condition("it's your turn" if t["w"] == "your turn" else "it's an opponent's turn")
            once = once or bool(t["once"])
            if condition is None:
                return None
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
        elif (nm := _NAMED_INSTEAD.fullmatch(s)) and not instead and len(options) == 1:  # -- named permanents (wave 35C) --
            more = _effect_options("Add " + nm.group("add"), identity)
            if more is None or len(more) != 1:
                return None
            instead_if, instead = (("@named", nm.group("a")), ("@named", nm.group("b"))), more
        elif (ci := _CONTROL_INSTEAD.fullmatch(s)) and not instead and count is None:  # -- kicked / instead (wave 4G) --
            more = _effect_options("A" + ci.group("add")[1:], identity)
            if more is None or not all(more) or any(x not in ALL_MANA for opt in (*options, *more) for x in opt):
                return None  # (plain mana only: no chosen color, no "a land could produce")
            marker = ("@power", ci.group("p")) if ci.group("p") else \
                ("@count", _COUNT_TYPES[ci.group("what").rstrip("s")], str(_NUM[ci.group(1)]))
            instead_if, instead = (marker,), more
        elif (ot := _OWN_COUNTER_TRIPLE.fullmatch(s)) and not instead and options == (("LANDS",),):  # -- most-played cards (wave 51F) --
            instead_if, instead = (("@counter", ot["k"]),), (("LANDS",) * 3,)
        elif (oc := _OWN_COUNTER_INSTEAD.fullmatch(s)) and not instead and len(options) == 1:  # -- opening hand (wave 18C) --
            more = _effect_options("A" + oc.group("add")[1:], identity)
            if more is None or not all(more):
                return None
            instead_if, instead = (("@counter", oc.group("k")),), more
        elif (si := _STATUS_INSTEAD.fullmatch(s)) and not instead and len(options) == 1:  # -- designations (wave 45B) --
            more = _effect_options("A" + si["add"][1:], identity)
            if more is None or len(more) != 1:
                return None
            instead_if, instead = (("@status", "initiative" if si["i"] else "completed_dungeon"),), more
        elif (pl := _PLAYED_LAND.fullmatch(s)) and not instead and len(options) == 1:  # -- this-turn history (wave 4D) --
            more = _effect_options("Add " + pl.group("add"), identity)
            if more is None or len(more) != 1:
                return None
            instead_if, instead = (PLAYED_LAND,), more
        elif (rider_json := _mana_units.rider(s)) is not None:  # -- mana provenance (wave 18B) --
            on_spend.append(rider_json)
        else:
            if m_unc := re.fullmatch(r"(Spend this mana only to cast .+?), and that spell can't be countered", s):
                s = m_unc.group(1)  # (Cavern of Souls, Delighted Halfling: the restriction and a rider on any spell it pays for)
                on_spend.append(json.dumps({"kind": "uncounterable", "spell": "sel:{\"zones\":[\"stack\"]}"}, sort_keys=True))
            q = spend_kind(s)  # (-- refused copy/mana (wave 3R3) -- the general restriction grammar)
            if q is None or spend_only is not None:
                return None  # a rider the engine doesn't know: leave the ability manual
            spend_only, spend_text = q, s + "."
    if spend_only is not None and from_hand:
        return None  # (-- wave 18B -- activated from the hand by mana_riders.activate_from_hand, which adds plain mana: manual)
    return ManaAbility(tap=tap, sacrifice_self=sacrifice, options=options, extra_cost=", ".join(extra),
                       riders=tuple(riders), spend_only=spend_only, once_per_turn=once, condition=condition,
                       count=count, chooses=chooses, instead_if=instead_if, instead=instead, self_counter=self_counter,
                       from_hand=from_hand, on_spend=tuple(on_spend), spend_text=spend_text, delayed_effects=delayed_effects,
                       from_graveyard=any(c.kind == _costs.EXILE_FROM_GRAVEYARD and c.selector is None
                                          for c in _costs.parse_ability_cost(", ".join(extra), card_name=card_name).components))


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
    snow: bool = False  # -- snow mana (wave 7E) -- a snow permanent: its mana can pay {S} (107.4h)
    generic_allowed: tuple[bool, ...] = ()  # Parallel to options; empty preserves unrestricted legacy sources.
    producer_facts: tuple[tuple[ProducerFact | None, ...], ...] = ()
    ability_options: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.ability_options and len(self.ability_options) != len(self.options):
            raise ValueError('Every source option needs its original ability option index')
        if self.producer_facts and (len(self.producer_facts) != len(self.options)
                or any(len(profile) != len(option) for profile, option in zip(self.producer_facts, self.options, strict=True))):
            raise ValueError('Every source output position needs its own producer fact')

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
    # -- mana provenance (wave 18B) -- each tapped source with the option it produced, in order ("unit:<id>" = a pool unit spent)
    slots: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)
    # -- mana provenance (wave 18B) -- set by ``mana_units.settle``: the source tags of each mana spent, and its riders (source, rider)
    tags: list[list[str]] = field(default_factory=list)
    snow_spent: dict[str, int] = field(default_factory=dict)  # Actual snow-source mana by color/type.
    sources: list[str] = field(default_factory=list)  # exact objects that produced mana actually spent
    riders: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    filters: list[tuple[str, int, tuple[str, ...], ManaCost]] = field(default_factory=list)  # activate before paying the actual cost

    auxiliary_life: int = 0  # Life paid to activate upstream mana sources, not this final cost.
    allocation: list[SpentClass] | None = None  # Exact consumed unit classes, absent in legacy/unrestricted payments.
    selected_options: list[tuple[str, int]] = field(default_factory=list)
    ability_options: list[tuple[str, int]] = field(default_factory=list)

    def delta(self) -> dict[str, int]:
        out = dict(self.produced)
        for k, v in self.spent.items():
            out[k] = out.get(k, 0) - v
        return {k: v for k, v in out.items() if v}


MAX_SEARCH = 20000
Chosen = list[tuple[Source, int]]
Found = tuple[dict[str, int], Chosen]


def _solve(reqs: list[tuple[str, ...]], generic: int, pool: dict[str, int], sources: list[Source]
           ) -> Found | None:
    """DFS over coloured/hybrid requirements; generic mana is paid last from whatever is left.
    Returns (units left over after paying, sources tapped with the option used)."""
    budget = [MAX_SEARCH]

    def generic_from(units: dict[str, int], remaining: list[Source], n: int, chosen: Chosen) -> Found | None:
        units = dict(units)
        # tap the sources that give the most mana first (Sol Ring before a Forest)
        for src in sorted(remaining, key=lambda s: (s.rank >= 0, not s.preferred, -max(len(o) for o in s.options), s.flexibility, s.rank)):
            if sum(units.values()) >= n:
                break
            oi = max(range(len(src.options)), key=lambda i: len(src.options[i]))
            opt = src.options[oi]
            for m in opt:
                units[m] = units.get(m, 0) + 1
            chosen = [*chosen, (src, oi)]
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
            alt = _pay_one(units, remaining, chosen, req[1:])
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

    if len(reqs) < 256:
        return dfs(0, {k: v for k, v in pool.items() if v > 0}, sources, [], 0)

    # The number of payable symbols is not a Python call-stack limit. Preserve the same
    # DFS branch order and budget for large costs using suspended child iterators.
    State = tuple[int, dict[str, int], list[Source], Chosen, int]

    def children(state: State) -> Iterator[State]:
        i, units, remaining, chosen, extra_generic = state
        req = reqs[i]
        if req[0].isdigit():
            for u2, rem2, ch2 in _pay_one(units, remaining, chosen, req[1:]):
                yield i + 1, u2, rem2, ch2, extra_generic
            yield i + 1, units, remaining, chosen, extra_generic + int(req[0])
        else:
            for u2, rem2, ch2 in _pay_one(units, remaining, chosen, req):
                yield i + 1, u2, rem2, ch2, extra_generic

    pending: list[Iterator[State]] = [iter([(0, {k: v for k, v in pool.items() if v > 0}, sources, [], 0)])]
    while pending:
        state = next(pending[-1], None)
        if state is None:
            pending.pop()
            continue
        budget[0] -= 1
        if budget[0] < 0:
            return None
        i, units, remaining, chosen, extra_generic = state
        if i == len(reqs):
            if (found := generic_from(units, remaining, generic + extra_generic, chosen)) is not None:
                return found
        else:
            pending.append(children(state))
    return None


def _pay_one(units: dict[str, int], remaining: list[Source], chosen: Chosen, req: tuple[str, ...]
             ) -> Iterator[tuple[dict[str, int], list[Source], Chosen]]:
    """Ways to pay one symbol that accepts any colour in ``req``: from the pool, else by tapping a source."""
    for color in req:
        if units.get(color, 0) > 0:
            new = dict(units)
            new[color] -= 1
            yield new, remaining, chosen
    for j, src in enumerate(remaining):
        for oi, opt in enumerate(src.options):
            if req == ('B', '@X') and src.abilities and src.abilities[oi] < 0:
                continue  # A convoke contribution is not actual black mana spent on X.
            # (-- snow mana (wave 7E) -- {S}: any mana of a snow source, 107.4h)
            wanted = opt[0] if req == (SNOW,) and src.snow and opt else next((c for c in req if c in opt), None)
            if wanted is None:
                continue
            new = dict(units)
            for m in opt:
                new[m] = new.get(m, 0) + 1
            new[wanted] -= 1
            yield new, remaining[:j] + remaining[j + 1:], [*chosen, (src, oi)]


def solve(cost: ManaCost, pool: dict[str, int], sources: list[Source], *, life: int = 0) -> Payment:
    """Find a payment for ``cost`` (X already fixed). Raises ManaError if there is none."""
    mixed_snow = any(source.producer_facts and any(
        (fact is not None and 'Snow' in fact.tags) != source.snow
        for profile in source.producer_facts for fact in profile) for source in sources)
    snow_due = SNOW in cost.colored or any(SNOW in symbols for symbols in cost.hybrid)
    if ((mixed_snow and snow_due)
            or any(s.generic_allowed and not all(s.generic_allowed) for s in sources)
            or (cost.allocation is not None and any(row.producer is not None
                for row in (*cost.allocation.symbols, *cost.allocation.phyrexian)))):
        from app.rules import mana_allocation_masks

        return mana_allocation_masks.solve(cost, pool,
            [mana_allocation_masks.MaskedSource(s, s.generic_allowed) for s in sources], life=life).payment
    if cost.unsupported:
        raise ManaError(f"Can't pay {' '.join('{' + s + '}' for s in cost.unsupported)} automatically")
    # (review 18B: mana already in the pool — mana_units' pseudo-sources, rank -1 — before anything is tapped, as the plain pool)
    ordered = sorted(sources, key=lambda s: (s.rank >= 0, not s.preferred, s.flexibility, s.rank, -max(len(o) for o in s.options)))
    base = [(c,) for c in cost.colored] + sorted(cost.hybrid, key=len)
    # Phyrexian symbols with mana first, then one more with 2 life each time (107.4f: each symbol on its own; wave 18B: K'rrik too;
    # review 18B: any k of them, so {W/P}{U/P} with only {W} pays 2 life, not 4)
    from itertools import combinations

    phy = cost.phyrexian
    by_life = {tuple(sorted(phy[i] for i in ix)): ix for k in range(len(phy) + 1) for ix in combinations(range(len(phy)), k)}
    attempts = [(base + [tuple(c.split("/")) for i, c in enumerate(phy) if i not in ix], 2 * len(ix)) for ix in by_life.values()]
    for reqs, life_cost in attempts:
        if life_cost and life_cost > life:  # 119.4 (wave 29C): the life total only has to be at least the payment — all of it may be paid
            continue
        found = _solve(reqs, cost.generic, pool, ordered)
        if found is None:
            continue
        left, chosen = found
        payment = Payment(life=life_cost)
        for src, oi in chosen:
            opt = src.options[oi]
            payment.selected_options.append((src.card_id, oi))
            if src.ability_options:
                payment.ability_options.append((src.card_id, src.ability_options[oi]))
            payment.slots.append((src.card_id, opt))
            payment.tapped.append(src.card_id)
            if src.sacrifice:
                payment.sacrificed.append(src.card_id)
            if src.abilities:
                payment.used.append((src.card_id, src.abilities[oi]))
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
    elif text.endswith(" of that color") and not source:  # -- most-played cards (wave 51F) -- "monocolored spells of that color" (Throne of Eldraine): the color chosen as it entered
        out["chosen_color"] = True
        text = text[: -len(" of that color")]
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
        elif w == "kicked":  # -- activated sweep (wave 17B) -- "kicked spells" (702.33): casting.Purpose.kicked
            out["kicked"] = True
        elif w[:1].isupper() and (_known_subtype(w) or _known_subtype(bare)):
            subs.append(w if _known_subtype(w) else bare)
        elif w[:1].isupper() and i + 1 < len(tokens) and tokens[i + 1] == "planeswalker":
            subs.append(w)  # (a planeswalker type: "a Chandra planeswalker spell", 205.3j)
        elif (w in ("source", "sources", "permanent", "permanents") and source) \
                or (w in ("spell", "spells") and not source and out.get("chosen")):  # (wave 51C: "a spell of the chosen type" (Eclipsed Realms): any spell with that creature type)
            pass
        else:
            return None
        i += 1
    if not (types or subs or supers or "color" in out or "non" in out or out.get("kicked") or out.get("chosen")):
        return None
    if out.get("chosen") and types not in ([], ["Creature"]):  # (wave 51C: no card type named: any spell / source of the chosen creature type)
        return None
    if out.get("chosen_color") and (out.get("color") != "monocolored" or types or subs or supers):
        return None
    if types:
        out["types"] = types
    if subs:
        out["subtypes"] = subs
    if supers:
        out["supertypes"] = supers
    return out


# -- mana provenance (wave 18B) -- what a spell is besides its types: "spells with mana value 5 or greater", "spells with {X} in their
# mana costs", "a spell with devoid" / "that has freerunning", "creature spells with no abilities", "spells you don't own" (601.2h: the
# spell's characteristics and who owns it are known as it is paid)
_SPELL_WITH: list[tuple[re.Pattern[str], Any]] = [
    (re.compile(r"^(?P<pre>.*?) ?spells? with mana value (?P<n>\d+)_ge$"), lambda m: {"mv_min": int(m["n"])}),
    (re.compile(r"^(?P<pre>.*?) ?spells? with \{X\} in (?:their|its) mana costs?$"), lambda m: {"has_x": True}),
    (re.compile(r"^(?P<pre>.*?) ?spells? (?:with|that has) (?P<kw>devoid|freerunning|flash|haste)$"), lambda m: {"kw": m["kw"]}),
    (re.compile(r"^(?P<pre>.*?) ?spells? with no abilities$"), lambda m: {"no_abilities": True}),
    (re.compile(r"^(?P<pre>.*?) ?spells? you don't own$"), lambda m: {"not_own": True}),
]


def _alts(phrase: str, *, source: bool) -> list[dict[str, object]] | None:
    p = re.sub(r"^(?:an?|one or more) ", "", phrase.strip())
    p = re.sub(r"(\d+) or greater", r"\1_ge", p)  # (its "or" isn't an alternative)
    parts = [x for x in re.split(r",? and/or |,? or |, and |, | and ", p) if x]
    out = []
    for part in parts:
        part = re.sub(r"^(?:an?) ", "", part)
        extra: dict[str, object] = {}
        if not source:
            for rx, make in _SPELL_WITH:
                if (w := rx.fullmatch(part)) is not None:
                    extra, part = make(w), w["pre"]
                    break
        if not source:  # ("instant and sorcery spells": the noun may come once, at the end)
            part = re.sub(r" spells?(?= of the chosen type$| of that color$)| spells?$", "", part)
        alt = _alt(part, source=source) if part or not extra else {}
        if alt is None:
            return None
        out.append({**alt, **extra})
    return out or None


_GENERIC_SPEND = re.compile(
    r"^Spend this mana only to (?:(?P<cast>cast (?P<spells>.+?))(?:,? (?:or|and) (?:to )?(?P<act>activate (?:an ability|abilities)"  # (wave 34B: ", or to activate" — Brotherhood Headquarters)
    r"(?: of (?P<src>.+))?))?|(?P<act2>activate (?:an ability|abilities)(?: of (?P<src2>.+?))?)(?: or (?:to )?cast (?P<spells2>.+))?)$")


# -- activated sweep (wave 17B) -- where the spell is cast from: "Spend this mana only to cast spells from exile / a spell from your
# graveyard / spells with flashback from a graveyard"; "This mana can't be spent to cast spells from your hand" (the zone is the
# one the spell is cast from, 601.2a; casting.Purpose.zone)
_ORIGIN = re.compile(r"^Spend this mana only to cast (?:a spell|spells)(?: with (?P<kw>flashback))? from (?P<z>exile|your graveyard|a graveyard)$")


def spend_kind(s: str) -> str | None:
    """A "Spend this mana only to …" / "This mana can't be spent to …" sentence (no final period) as the restriction
    ``casting.spend_allowed`` reads (None: not one the payer checks)."""
    for pattern, kind in _SPEND:
        if sm := pattern.fullmatch(s):
            return f"type:{sm.group('t')}" if kind == "type" else kind
    return parse_spend(s)


# -- mana for special abilities (wave 19E) -- actions that aren't casting a spell or activating an ability of a source, with the
# ``casting.Purpose.special`` that names them: "activate an equip ability", "turn permanents face up", "foretell a card",
# "activate power-up abilities"
_SPECIAL_SPEND = {r"activate (?:an equip ability|equip abilities)": "equip", r"turn (?:a )?(?:permanents?|creatures?) face up": "turn_up",
                  r"foretell (?:a card|cards)(?: from your hand)?": "foretell", r"activate power-up abilities": "power_up"}


def _special_split(s: str) -> tuple[str, list[str]]:
    """The sentence without its special actions, and those (the list "cast X, turn permanents face up, or activate abilities")."""
    found: list[str] = []
    for pattern, name in _SPECIAL_SPEND.items():
        for rx in (rf"(?:, or | or |, ){pattern}", rf"(?<=only to ){pattern}(?:, or | or |, )"):
            s, n = re.subn(rx, "", s, count=1)
            if n:
                found.append(name)
                break
        else:
            if re.fullmatch(rf"Spend this mana only to {pattern}", s):
                return "Spend this mana only to", [name]
    return s, found


def parse_spend(sentence: str) -> str | None:
    """A general "Spend this mana only to …" restriction as "q:<json>" (None: not one the payer checks)."""
    import json

    from app.rules import mixed_mana_restrictions

    s = sentence.strip().rstrip(".")
    if s.lower() == "spend this mana only to cast spells with exactly three colors":
        return "q:" + json.dumps({"cast": [{"color_count": 3}], "ability": None}, sort_keys=True)
    from app.rules import contextual_mana_outcomes
    if (contextual := contextual_mana_outcomes.restriction(s)) is not None:
        return 'q:' + json.dumps(contextual, sort_keys=True)
    if (mixed := mixed_mana_restrictions.parse(s)) is not None:
        return 'q:' + json.dumps(mixed, sort_keys=True)
    s, special = _special_split(s)
    if special:
        rest = None if s == "Spend this mana only to" else parse_spend(s)
        base = json.loads(rest[2:]) if rest is not None else {"cast": None, "ability": None} if s == "Spend this mana only to" else None
        return None if base is None else "q:" + json.dumps({**base, "special": sorted(special)}, sort_keys=True)
    if s == "Spend this mana only on costs that contain {X}":  # -- mana provenance (wave 18B) -- casting.Purpose.cost_x
        return "q:" + json.dumps({"cast": None, "ability": None, "cost_x": True}, sort_keys=True)
    if s == "This mana can't be spent to cast spells":
        return "q:" + json.dumps({"cast": None, "ability": "any"}, sort_keys=True)
    if s == "This mana can't be spent to cast spells from your hand":
        return "q:" + json.dumps({"cast": [{"not_zone": "hand"}], "ability": "any"}, sort_keys=True)
    if s in ("Spend this mana only to cast a spell from anywhere other than your hand", "Spend this mana only to cast spells from anywhere other than your hand"):
        # -- static_other (wave 42A) -- Mm'menon, the Right Hand: a spell cast from any zone but its caster's hand (601.2a), and no ability
        return "q:" + json.dumps({"cast": [{"not_zone": "hand"}], "ability": None}, sort_keys=True)
    if m := _ORIGIN.fullmatch(s):
        alt: dict[str, object] = {"zone": "exile" if m["z"] == "exile" else "graveyard", "own": m["z"] == "your graveyard"}
        if m["kw"]:
            alt["kw"] = m["kw"]
        return "q:" + json.dumps({"cast": [alt], "ability": None}, sort_keys=True)
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
    from app.rules.contextual_mana_outcomes import has_foretell

    if alt.get("color_count") is not None and len(ch.colors) != alt["color_count"]:
        return False
    if alt.get('foretell') and not has_foretell(ch):
        return False
    if alt.get('colored_without_x') and (not ch.colors or '{X}' in ch.mana_cost):
        return False
    types: frozenset[str] = ch.types
    colors: frozenset[str] = ch.colors
    if alt.get('on_battlefield') and not ch.on_battlefield:
        return False
    if alt.get('face_down') and not ch.face_down:
        return False
    if alt.get('any_subtypes') and not set(alt['any_subtypes']).intersection(ch.subtypes):
        return False
    if any(t not in types for t in alt.get("types") or []):
        return False
    if any(t not in ch.subtypes for t in alt.get("subtypes") or []):
        return False
    if any(t not in ch.supertypes for t in alt.get("supertypes") or []):
        return False
    if any(t in types for t in alt.get("non") or []):
        return False
    if alt.get("kw") and alt["kw"] not in ch.keywords:
        return False
    if alt.get("mv_min") is not None and ch.mana_value < alt["mv_min"]:  # -- mana provenance (wave 18B) --
        return False
    if alt.get("has_x") and "{X}" not in ch.mana_cost:
        return False
    if alt.get("no_abilities") and ch.abilities:
        return False
    if alt.get("mono_color") and colors != {alt["mono_color"]}:  # -- most-played cards (wave 51F) -- "monocolored spells of that color": exactly the chosen color
        return False
    color = alt.get("color")
    if color == "colorless" and colors:
        return False
    if color == "multicolored" and len(colors) < 2:
        return False
    return not (color == "monocolored" and len(colors) != 1)
# -- end refused copy/mana (wave 3R3) --
