"""Costs of activated abilities (the text before the colon), as data.

``parse_ability_cost("{2}, {T}, Sacrifice Mind Stone")`` → ``AbilityCost(mana="{2}", tap=True,
sacrifice_self=True, components=(…))``. Each comma-separated part is one :class:`CostComponent`
(CR 118.1 / 602.2b: an activation cost may be any mix of mana, tapping or untapping the source,
sacrificing, discarding, exiling, paying life, removing counters, returning permanents …). A part
that names objects to choose ("Sacrifice another creature", "Discard a land card", "Tap an
untapped Elf you control") carries a selector (app/rules/selectors.py) the payer's choices must
match (casting.cost_choices). Anything the engine can't pay by itself is listed in
``unsupported``; the ability is then refused with a clear message and can be done by hand.

Kicker (702.33) is parsed here too: :func:`kicker_cost` reads a "Kicker {cost}" / "Multikicker
{cost}" keyword line.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.rules.oracle import AbilityText

# 107.4: mana symbols, including multi-digit generic mana ({10}, {12}) and hybrid / Phyrexian
# ({S} snow mana isn't modeled: it stays unsupported).
_MANA_ONLY = re.compile(r"^(\{(?:\d+|[WUBRGCX]|[WUBRG2]/[WUBRGP]|[WUBRG]/[WUBRG]/P)\})+$")
_SELF = r"(?:this \w+|it|~)"
_SAC_SELF = re.compile(r"^Sacrifice (this \w+|it|~|(?P<name>.+))$")
_LIFE = re.compile(r"^Pay (?P<n>\d+) life$")
_ENERGY = re.compile(r"^Pay (?:(?P<symbols>(?:\{E\})+)|(?P<n>\w+) \{E\})$")
_REMOVE = re.compile(
    r"^Remove (?P<n>a|an|one|two|three|four|five|\d+) (?P<kind>[\w+/\-]+) counters? from (this \w+|it|~|(?P<name>.+))$"
)
_N = r"(?P<n>a|an|another|one|two|three|four|five|six|\d+)"
_SAC_CHOSEN = re.compile(rf"^Sacrifice {_N} (?P<what>.+)$")
_DISCARD = re.compile(rf"^Discard {_N} (?P<what>(?:[\w\-]+ )*cards?)(?P<random> at random)?$")
_EXILE_SELF_GY = re.compile(rf"^Exile {_SELF} from your graveyard$")
_EXILE_SELF = re.compile(rf"^Exile {_SELF}$")
_EXILE_GY = re.compile(rf"^Exile {_N} (?P<what>(?:[\w\-]+ )*cards? from your graveyard)$")
_RETURN_SELF = re.compile(rf"^Return {_SELF} to its owner's hand$")
_RETURN = re.compile(rf"^Return {_N} (?P<what>.+? you control) to (?:its|their) owner's hands?$")
_TAP_OTHER = re.compile(rf"^Tap {_N} (?P<another>another )?untapped (?P<what>.+ you control)$")
_REMOVE_CHOSEN = re.compile(
    r"^Remove (?P<n>a|an|one|two|three|\d+) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? from (?:a|an|another) (?P<what>.+)$")
_WORDS = {"a": 1, "an": 1, "another": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}

# Component kinds (the parts of a cost, 118.1)
MANA, TAP, UNTAP, SACRIFICE, DISCARD, PAY_LIFE, PAY_ENERGY = "MANA", "TAP", "UNTAP", "SACRIFICE", "DISCARD", "PAY_LIFE", "PAY_ENERGY"
EXILE, EXILE_FROM_GRAVEYARD, REMOVE_COUNTER, RETURN_PERMANENT = "EXILE", "EXILE_FROM_GRAVEYARD", "REMOVE_COUNTER", "RETURN_PERMANENT"
TAP_OTHER, REVEAL, LOYALTY, OTHER = "TAP_OTHER", "REVEAL", "LOYALTY", "OTHER"


@dataclass(frozen=True)
class CostComponent:
    """One part of a cost. ``selector`` (a selector key) is set when the payer chooses the objects
    ("Sacrifice another creature": amount 1, selector for "another creature you control");
    None means the source itself (or, for MANA / PAY_LIFE / LOYALTY, no object at all)."""

    kind: str
    amount: int = 1
    selector: str | None = None
    counter: str | None = None  # REMOVE_COUNTER: the kind of counter
    random: bool = False  # "Discard a card at random"
    text: str = ""

    @property
    def chosen(self) -> bool:
        """Does paying it need a choice of objects (casting.cost_choices)?"""
        return self.selector is not None and not self.random


@dataclass(frozen=True)
class AbilityCost:
    mana: str = ""  # mana symbols, e.g. "{2}{G}"
    tap: bool = False
    untap: bool = False  # {Q} (107.6)
    sacrifice_self: bool = False
    life: int = 0
    remove_counters: tuple[tuple[str, int], ...] = ()  # (kind, amount) from the source itself
    loyalty: int | None = None  # +N / −N / 0 for planeswalker abilities
    loyalty_x: bool = False  # −X: remove X loyalty counters, X chosen as it's activated (107.3k)
    unsupported: tuple[str, ...] = field(default_factory=tuple)
    components: tuple[CostComponent, ...] = ()
    graveyard_only: bool = False  # -- reanimation (wave 3R) -- its effect moves this card out of your graveyard (113.6m)

    @property
    def basic(self) -> bool:
        """Only mana, {T}, sacrificing the source, life and the source's counters (what mana
        abilities pay by themselves, casting.produce)."""
        return not self.unsupported and all(
            c.kind in (MANA, TAP, PAY_LIFE, LOYALTY) or (c.kind in (SACRIFICE, REMOVE_COUNTER) and c.selector is None)
            for c in self.components)

    @property
    def choices(self) -> list[tuple[int, CostComponent]]:
        """The components whose objects the payer chooses, with their index."""
        return [(i, c) for i, c in enumerate(self.components) if c.chosen]

    @property
    def from_graveyard(self) -> bool:
        """113.6m: "Exile this card from your graveyard" — the ability works only from there."""
        return self.graveyard_only or any(c.kind == EXILE_FROM_GRAVEYARD and c.selector is None for c in self.components)

    def of_kind(self, kind: str) -> list[CostComponent]:
        return [c for c in self.components if c.kind == kind]


def _n(word: str) -> int:
    return _WORDS[word] if word in _WORDS else int(word)


def _selector(phrase: str, *, zone: str, other: bool = False) -> str | None:
    """The selector key for a cost's noun phrase, or None if it isn't a plain one we understand."""
    from dataclasses import replace

    from app.rules import selectors

    if phrase in ("token", "tokens"):
        phrase = "token permanent"
    sel = selectors.parse(phrase)
    if sel is None or sel.player is not None or sel.extras and any(
            e in ("enchanted", "equipped") for e in sel.extras) or sel.attacking or sel.blocking:
        return None
    if zone == "battlefield":
        if sel.card or sel.zones != ("battlefield",) or sel.controller == "opponent" or sel.owner is not None:
            return None
        sel = replace(sel, controller="you")  # 701.21a: only permanents you control
    elif zone == "hand":
        if not sel.card or sel.zones not in ((), ("hand",)) or sel.controller or sel.owner:
            return None
        sel = replace(sel, zones=("hand",), zone_owner="you")
    elif zone == "graveyard":
        if not sel.card or sel.zones != ("graveyard",) or sel.zone_owner != "you" or sel.controller or sel.owner:
            return None
    if other:
        sel = replace(sel, other=True)
    return sel.key()


def _component(part: str, card_name: str) -> CostComponent | None:
    """One comma-separated part of an activation cost, or None when the engine can't pay it."""
    if part == "{T}":
        return CostComponent(TAP, text=part)
    if part == "{Q}":
        return CostComponent(UNTAP, text=part)
    if _MANA_ONLY.match(part):
        return CostComponent(MANA, text=part)
    if (m := _SAC_SELF.match(part)) and (not m.group("name") or m.group("name") == card_name):
        return CostComponent(SACRIFICE, text=part)
    if m := _LIFE.match(part):
        return CostComponent(PAY_LIFE, amount=int(m["n"]), text=part)
    if m := _ENERGY.match(part):
        n = m["symbols"].count("{E}") if m["symbols"] else _WORDS.get(m["n"].lower()) or (int(m["n"]) if m["n"].isdigit() else 0)
        return CostComponent(PAY_ENERGY, amount=n, text=part) if n else None
    if (m := _REMOVE.match(part)) and (not m.group("name") or m.group("name") == card_name):
        return CostComponent(REMOVE_COUNTER, amount=_n(m["n"]), counter=m["kind"], text=part)
    if _EXILE_SELF_GY.match(part):
        return CostComponent(EXILE_FROM_GRAVEYARD, text=part)
    if _EXILE_SELF.match(part):
        return CostComponent(EXILE, text=part)
    if _RETURN_SELF.match(part):
        return CostComponent(RETURN_PERMANENT, text=part)
    if m := _SAC_CHOSEN.match(part):
        key = _selector(m["what"], zone="battlefield", other=m["n"] == "another")
        return CostComponent(SACRIFICE, amount=_n(m["n"]), selector=key, text=part) if key else None
    if m := _DISCARD.match(part):
        if m["n"] == "another":
            return None
        key = _selector(m["what"], zone="hand")
        return CostComponent(DISCARD, amount=_n(m["n"]), selector=key, random=bool(m["random"]), text=part) if key else None
    if m := _EXILE_GY.match(part):
        key = _selector(m["what"], zone="graveyard", other=m["n"] == "another")
        return CostComponent(EXILE_FROM_GRAVEYARD, amount=_n(m["n"]), selector=key, text=part) if key else None
    if m := _RETURN.match(part):
        key = _selector(m["what"], zone="battlefield", other=m["n"] == "another")
        return CostComponent(RETURN_PERMANENT, amount=_n(m["n"]), selector=key, text=part) if key else None
    if m := _TAP_OTHER.match(part):
        key = _selector("untapped " + m["what"], zone="battlefield", other=bool(m["another"]) or m["n"] == "another")
        return CostComponent(TAP_OTHER, amount=_n(m["n"]), selector=key, text=part) if key else None
    if m := _REMOVE_CHOSEN.match(part):
        other = part.split(" from ", 1)[1].startswith("another ")
        key = _selector(m["what"], zone="battlefield", other=other)
        return CostComponent(REMOVE_COUNTER, amount=_n(m["n"]), counter=m["kind"], selector=key, text=part) if key else None
    return None


def parse_ability_cost(cost: str, *, card_name: str = "", loyalty: bool = False) -> AbilityCost:
    if loyalty:
        raw = cost.strip().replace("−", "-")
        if raw.upper() == "-X":
            return AbilityCost(loyalty_x=True, components=(CostComponent(LOYALTY, text=cost),))
        if raw.upper().lstrip("+-") == "X":
            return AbilityCost(unsupported=(cost,))
        return AbilityCost(loyalty=int(raw), components=(CostComponent(LOYALTY, amount=int(raw), text=cost),))
    components: list[CostComponent] = []
    unsupported: list[str] = []
    for part in (p.strip() for p in cost.split(",")):
        if not part:
            continue
        found = _component(_self_text(part, card_name), card_name)
        if found is None:
            unsupported.append(part)
        else:
            components.append(found)
    kinds = [c.kind for c in components]
    if kinds.count(TAP) + kinds.count(UNTAP) > 1:
        unsupported.append(cost)  # ("{T}, {Q}" isn't a thing; never guess)
    return AbilityCost(
        mana="".join(c.text for c in components if c.kind == MANA),
        tap=TAP in kinds, untap=UNTAP in kinds,
        sacrifice_self=any(c.kind == SACRIFICE and c.selector is None for c in components),
        life=sum(c.amount for c in components if c.kind == PAY_LIFE),
        remove_counters=tuple((c.counter or "", c.amount) for c in components
                              if c.kind == REMOVE_COUNTER and c.selector is None),
        unsupported=tuple(unsupported), components=tuple(components))


def _self_text(part: str, card_name: str) -> str:
    """The part with the card's own name (or "this creature" …) written as ~ (scripts.self_text)."""
    if not card_name:
        return part
    from app.rules.scripts import self_text  # scripts imports this module

    return self_text(part, card_name)


# -- kicker (702.33) -------------------------------------------------------------------------
_KICKER = re.compile(r"^(?P<multi>multi)?kicker (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)


def kicker_line(line: str) -> bool:
    """Is this keyword line a kicker the engine pays ("Kicker {2}{R}", "Multikicker {1}")?"""
    m = _KICKER.fullmatch(line.strip().rstrip("."))
    return m is not None and "{X}" not in m["cost"].upper() and _MANA_ONLY.match(m["cost"]) is not None


@dataclass(frozen=True)
class Kicker:
    cost: str  # mana symbols, e.g. "{2}{R}"
    multi: bool = False  # 702.33c multikicker: any number of times


def kicker_cost(abilities: Iterable[AbilityText]) -> Kicker | None:
    """702.33a / 702.33c: the card's "Kicker {cost}" or "Multikicker {cost}" line (mana only), or
    None. Two kicker costs ("Kicker {1}{U} and/or {2}{B}", 702.33b), non-mana kicker costs
    ("Kicker—Sacrifice a land") and X in the cost stay manual."""
    found: list[Kicker] = []
    for ab in abilities:
        if ab.kind != "keywords" or not ({"kicker", "multikicker"} & set(ab.keywords)):
            continue
        m = _KICKER.fullmatch(ab.text.strip().rstrip("."))
        if m is None or not kicker_line(ab.text):
            return None
        found.append(Kicker(m["cost"], multi=bool(m["multi"])))
    return found[0] if len(found) == 1 else None


# -- costs (wave 3$) -- additional costs to cast a spell (118.8, 601.2b) ----------------------------------
_ADDITIONAL = re.compile(r"^as an additional cost to cast (?:this spell|~), (?P<cost>[^.]+)\.?$", re.IGNORECASE)
# What a spell's additional cost may be made of: parts with chosen objects (or life / energy). Never the
# source itself (a spell isn't on the battlefield to be sacrificed), tapping it, mana or counters on it.
_ADDITIONAL_KINDS = frozenset({SACRIFICE, DISCARD, PAY_LIFE, PAY_ENERGY, EXILE_FROM_GRAVEYARD, RETURN_PERMANENT, TAP_OTHER})


def additional_cost_text(line: str) -> str | None:
    """"As an additional cost to cast this spell, sacrifice a creature." → "sacrifice a creature"."""
    m = _ADDITIONAL.match(line.strip())
    return m["cost"] if m else None


def spell_additional_cost(abilities: Iterable[AbilityText]) -> AbilityCost | None:
    """The additional cost a spell's "As an additional cost to cast this spell, …" line asks (every
    such line, combined), or None. A line the grammar can't pay makes the spell manual (permissions
    .define_static returns no definition), so it is never read here."""
    parts: list[CostComponent] = []
    for ab in abilities:
        text = additional_cost_text(ab.text) if ab.kind != "keywords" else None
        found = parse_additional_cost(text) if text is not None else None
        if found is not None:
            parts += found.components
    return AbilityCost(components=tuple(parts), life=sum(c.amount for c in parts if c.kind == PAY_LIFE)) if parts else None


def parse_additional_cost(text: str) -> AbilityCost | None:
    """The parts of a spell's additional cost ("sacrifice a creature", "discard a card and pay 2 life",
    "exile a creature card from your graveyard") as an :class:`AbilityCost` (components only), or None
    when the engine can't pay it by itself ("you may …", "… or …" alternatives, X, a cost with no
    chosen object): the spell then stays manual rather than being cast without its cost (601.2b)."""
    text = text.strip()
    if text.lower().startswith("you may") or re.search(r"\bx\b", text, re.IGNORECASE) or "," in text:
        return None
    parts = [p.strip() for p in re.split(r" and (?=(?:sacrifice|discard|pay|exile|return|tap) )", text)]
    components: list[CostComponent] = []
    for part in parts:
        found = _component(part[:1].upper() + part[1:], "")
        if found is None or found.kind not in _ADDITIONAL_KINDS:
            return None
        if found.selector is None and found.kind not in (PAY_LIFE, PAY_ENERGY):
            return None
        components.append(found)
    return AbilityCost(components=tuple(components), life=sum(c.amount for c in components if c.kind == PAY_LIFE))
