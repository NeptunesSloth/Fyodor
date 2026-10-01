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
    r"^Remove (?P<n>a|an|one|two|three|four|five|six|seven|eight|\d+) (?P<kind>[\w+/\-]+) counters? from (this \w+|it|~|(?P<name>.+))$"
)
_N = r"(?P<n>a|an|another|one|two|three|four|five|six|seven|eight|nine|ten|thirteen|\d+)"  # (seven …: wave 4H)
_SAC_CHOSEN = re.compile(rf"^Sacrifice {_N} (?P<what>.+)$")
_DISCARD = re.compile(rf"^Discard {_N} (?P<what>(?:[\w\-]+ )*cards?)(?P<random> at random)?$")
_DISCARD_SELF = re.compile(r"^Discard (?:this card|~)$")  # -- ability words (wave 4F) -- channel (113.6m)
_EXILE_SELF_GY = re.compile(rf"^Exile {_SELF} from your graveyard$")
_EXILE_SELF = re.compile(rf"^Exile {_SELF}$")
_EXILE_GY = re.compile(rf"^Exile {_N} (?P<what>(?:[\w\-]+ )*cards? from your graveyard)$")
_RETURN_SELF = re.compile(rf"^Return {_SELF} to its owner's hand$")
_RETURN = re.compile(rf"^Return {_N} (?P<what>.+? you control) to (?:its|their) owner's hands?$")
_TAP_OTHER = re.compile(rf"^Tap {_N} (?P<another>another )?untapped (?P<what>.+ you control)$")
_REMOVE_CHOSEN = re.compile(
    r"^Remove (?P<n>a|an|one|two|three|\d+) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? from (?:a|an|another) (?P<what>.+)$")
_WORDS = {"a": 1, "an": 1, "another": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
          "seven": 7, "eight": 8, "nine": 9, "ten": 10, "thirteen": 13}  # (seven …: wave 4H, "Exile seven cards from your graveyard")
_ENERGY_WORDS = {**_WORDS, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "fifty": 50}  # (wave 3E: "Pay eight {E}")

# Component kinds (the parts of a cost, 118.1)
MANA, TAP, UNTAP, SACRIFICE, DISCARD, PAY_LIFE, PAY_ENERGY = "MANA", "TAP", "UNTAP", "SACRIFICE", "DISCARD", "PAY_LIFE", "PAY_ENERGY"
EXILE, EXILE_FROM_GRAVEYARD, REMOVE_COUNTER, RETURN_PERMANENT = "EXILE", "EXILE_FROM_GRAVEYARD", "REMOVE_COUNTER", "RETURN_PERMANENT"
TAP_OTHER, REVEAL, LOYALTY, OTHER = "TAP_OTHER", "REVEAL", "LOYALTY", "OTHER"
# -- activation costs (wave 4H) -- put counters (122.6; blight 701.68a), discard your hand, mill (701.17), exile from the
# top of your library, exert the source (701.43a); ANY_COUNTER: "Remove a counter from …" (the payer picks the kind)
PUT_COUNTER, DISCARD_HAND, MILL, EXILE_LIBRARY, EXERT = "PUT_COUNTER", "DISCARD_HAND", "MILL", "EXILE_LIBRARY", "EXERT"
COLLECT_EVIDENCE, FORAGE = "COLLECT_EVIDENCE", "FORAGE"  # 701.59a, 701.61a: the payer picks how many / which way
WAVE_4H_KINDS = frozenset({PUT_COUNTER, DISCARD_HAND, MILL, EXILE_LIBRARY, EXERT, COLLECT_EVIDENCE, FORAGE})
ANY_COUNTER = "*"


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
    x: bool = False  # -- counters & designations (wave 3E) -- "Pay X {E}": the X chosen as it's activated (107.3k)
    # -- activation costs (wave 4H) -- PAY_LIFE sized as it's paid: "half" ("Pay half your life, rounded up") or
    # "commander_colors" ("Pay life equal to the number of colors in your commanders' color identity", 903.4f)
    life_rule: str | None = None
    alt: str | None = None  # (wave 4H) "Sacrifice another creature or an artifact": a second selector, either matches
    named_self: bool = False  # (wave 4H) grandeur, "Discard another card named ~": a card with the source's name

    @property
    def chosen(self) -> bool:
        """Does paying it need a choice of objects (casting.cost_choices)?"""
        return (self.selector is not None and not self.random) or self.counter == ANY_COUNTER \
            or self.kind in (COLLECT_EVIDENCE, FORAGE)  # (wave 4H)

    @property
    def objects(self) -> int:
        """-- activation costs (wave 4H) -- how many objects a chosen part takes: one permanent for its counters
        ("Remove two +1/+1 counters from a creature you control", "Blight 2"), else ``amount`` (X: ``x``)."""
        return 1 if self.kind in (REMOVE_COUNTER, PUT_COUNTER) else self.amount

    @property
    def activation_only(self) -> bool:
        """-- activation costs (wave 4H) -- a part only an activated ability's activation pays (casting.activate_to_stack
        through app/rules/cost_payment.py): never a mana ability's (605: no stack, no X), an optional payment's or a
        spell's additional cost."""
        return self.kind in WAVE_4H_KINDS or (self.x and self.kind != PAY_ENERGY) or self.counter == ANY_COUNTER \
            or self.life_rule is not None or (self.kind == EXILE and self.selector is not None) \
            or self.alt is not None or self.named_self


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
    life_x: bool = False  # -- X sized by a count (wave 4K) -- a spell's "pay X life" (107.3a: X announced as it's cast)

    @property
    def basic(self) -> bool:
        """Only mana, {T}, sacrificing the source, life and the source's counters (what mana
        abilities pay by themselves, casting.produce)."""
        return not self.unsupported and not self.activation_only and all(  # (activation_only: wave 4H)
            c.kind in (MANA, TAP, PAY_LIFE, LOYALTY, PAY_ENERGY) or (c.kind in (SACRIFICE, REMOVE_COUNTER) and c.selector is None)
            for c in self.components)

    @property
    def activation_only(self) -> bool:
        """-- activation costs (wave 4H) -- does a part need an activated ability's own activation (CostComponent)?"""
        return any(c.activation_only for c in self.components)

    @property
    def x_chosen(self) -> bool:
        """-- activation costs (wave 4H) -- a part sized by an X announced as it's activated (107.3a, 107.3k):
        "Sacrifice X Treasures", "Remove X ki counters from this creature", "Pay X {E}"."""
        return any(c.x for c in self.components)

    @property
    def energy(self) -> int:
        """-- counters & designations (wave 3E) -- the fixed energy it pays (107.14; "Pay X {E}" not counted)."""
        return sum(c.amount for c in self.components if c.kind == PAY_ENERGY and not c.x)

    @property
    def choices(self) -> list[tuple[int, CostComponent]]:
        """The components whose objects the payer chooses, with their index."""
        return [(i, c) for i, c in enumerate(self.components) if c.chosen]

    @property
    def from_hand(self) -> bool:
        """-- ability words (wave 4F) -- 113.6m: "Discard this card" (channel: "{1}{R}, Discard this card: …") moves
        the card out of its owner's hand, so the ability works only there."""
        return any(c.kind == DISCARD and c.selector is None for c in self.components)

    @property
    def from_graveyard(self) -> bool:
        """113.6m: "Exile this card from your graveyard" — the ability works only from there."""
        return self.graveyard_only or any(c.kind == EXILE_FROM_GRAVEYARD and c.selector is None for c in self.components)

    @property
    def energy_x(self) -> bool:
        """-- counters & designations (wave 3E) -- "Pay X {E}": X is chosen as it's activated."""
        return any(c.kind == PAY_ENERGY and c.x for c in self.components)

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
        if m["n"] == "X":  # -- counters & designations (wave 3E) -- "Pay X {E}" (X chosen as it's activated)
            return CostComponent(PAY_ENERGY, amount=0, x=True, text=part)
        n = m["symbols"].count("{E}") if m["symbols"] else _ENERGY_WORDS.get(m["n"].lower()) or (int(m["n"]) if m["n"].isdigit() else 0)
        return CostComponent(PAY_ENERGY, amount=n, text=part) if n else None
    if (m := _REMOVE.match(part)) and (not m.group("name") or m.group("name") == card_name):
        return CostComponent(REMOVE_COUNTER, amount=_n(m["n"]), counter=m["kind"], text=part)
    if _EXILE_SELF_GY.match(part):
        return CostComponent(EXILE_FROM_GRAVEYARD, text=part)
    if _DISCARD_SELF.match(part):  # -- ability words (wave 4F) -- "Discard this card" (701.9a; 113.6m: from the hand)
        return CostComponent(DISCARD, text=part)
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
    cost = cost.replace("half your life, rounded up", "half your life rounded up")  # (one part: wave 4H)
    if card_name and "," in card_name:  # (wave 4H) "Discard another card named Korlash, Heir to Blackblade": one part
        cost = cost.replace(card_name, "~")
    for part in (p.strip() for p in cost.split(",")):
        if not part:
            continue
        found = _component(_self_text(part, card_name), card_name)
        if found is None:  # -- activation costs (wave 4H) --
            several = wave4h_parts(_self_text(part, card_name), card_name)
            if several is None:
                unsupported.append(part)
            else:
                components += several
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
        remove_counters=tuple((c.counter or "", c.amount) for c in components  # (X / any kind: cost_payment, wave 4H)
                              if c.kind == REMOVE_COUNTER and c.selector is None and not c.x and c.counter != ANY_COUNTER),
        unsupported=tuple(unsupported), components=tuple(components))


# -- activation costs (wave 4H) ------------------------------------------------------------------------------
# More parts of an activation cost (118.1, 602.2b → 601.2h), each with its legality check in app/rules/cost_payment.py
# (118.3: a cost that can't be paid fully can't be paid at all):
#   "Remove a counter from this creature" / "Remove two counters from ~" (any kinds: the payer picks, 122.1),
#   "Remove a counter from a creature you control", "Remove X ki counters from ~" (107.3a: X announced, at most what's there),
#   "Put a -1/-1 counter on this creature", "Put a -1/-1 counter on a creature you control", "Blight 2" (701.68a),
#   "Sacrifice X Treasures", "Tap X untapped artifacts you control", "Exile X cards from your graveyard" (107.3a),
#   "Discard your hand" (payable with an empty hand: Wizards ruling on Bomat Courier, 2016-09-20),
#   "Mill two cards" (701.17b), "Exile the top card of your library" (601.2h: paid last),
#   "Exile a creature you control", "Pay half your life, rounded up" (107.1a, 119.4),
#   "Pay life equal to the number of colors in your commanders' color identity" (903.4f: no commander, unpayable),
#   "Collect evidence 3" (701.59a: any number of graveyard cards with total mana value 3 or more), "Forage" (701.61a),
#   "Sacrifice another creature or an artifact" (either; "another" only for its own noun), grandeur's "Discard another
#   card named ~" (a card in your hand with the source's name), "Exert this creature" (701.43a-c),
#   and two parts joined by "and": "Remove three quest counters from this enchantment and sacrifice it",
#   "Sacrifice two lands and this artifact", "Sacrifice a creature and a Swamp".
_ANY_SELF = re.compile(rf"^Remove (?P<n>a|an|one|two|three|four|five) counters? from {_SELF}$")
_ANY_CHOSEN = re.compile(r"^Remove (?:a|one) counter from (?P<another>a|an|another) (?P<what>[^,]+ you control)$")
_X_SELF = re.compile(rf"^Remove X (?P<kind>[\w+/\-]+) counters from {_SELF}$")
_PUT_SELF = re.compile(rf"^Put {_N} (?P<kind>[\w+/\-]+) counters? on {_SELF}$")
_PUT_CHOSEN = re.compile(rf"^Put {_N} (?P<kind>[+-]\d+/[+-]\d+) counters? on (?P<another>a|an|another) (?P<what>[^,]+ you control)$")
_BLIGHT = re.compile(r"^Blight (?P<n>\d+)$")
_SAC_X = re.compile(r"^Sacrifice X (?P<what>.+)$")
_TAP_X = re.compile(r"^Tap X untapped (?P<what>.+ you control)$")
_EXILE_GY_X = re.compile(r"^Exile X (?P<what>(?:[\w\-]+ )*cards from your graveyard)$")
_MILL = re.compile(rf"^Mill (?:a card|{_N} cards)$")
_EXILE_TOP = re.compile(rf"^Exile the top (?:card|{_N} cards) of your library$")
_EXILE_CHOSEN = re.compile(rf"^Exile {_N} (?P<what>[^,]+ you control)$")
_EVIDENCE = re.compile(r"^Collect evidence (?P<n>\d+)$")
_SAC_OR = re.compile(r"^Sacrifice (?P<a>a|an|another) (?P<w1>[\w\-]+) or (?P<b>a|an|another) (?P<w2>[\w\-]+)$")  # (no article: refused)
_GRANDEUR = re.compile(r"^Discard another card named ~$")  # (grandeur, an ability word: 207.2c)
_HALF_LIFE = "Pay half your life rounded up"
_COMMANDER_LIFE = "Pay life equal to the number of colors in your commanders' color identity"
_AND = re.compile(r" and (?=(?:(?:sacrifice|exile|return|remove|discard|tap|put|pay) )?(?:(?:a|an|another|one|two|three|this|it|\d+)\b|~))")
_VERB = re.compile(r"^(?P<verb>Sacrifice|Exile|Return|Remove|Discard|Tap|Put|Pay) ")


def _x_part(kind: str, what: str, zone: str, text: str) -> CostComponent | None:
    key = _selector(what, zone=zone)
    return CostComponent(kind, amount=0, selector=key, x=True, text=text) if key else None


def _one_4h(part: str, card_name: str) -> CostComponent | None:
    """One more part (the list above), or None."""
    if m := _ANY_SELF.match(part):
        return CostComponent(REMOVE_COUNTER, amount=_n(m["n"]), counter=ANY_COUNTER, text=part)
    if m := _ANY_CHOSEN.match(part):
        key = _selector(m["what"], zone="battlefield", other=m["another"] == "another")
        return CostComponent(REMOVE_COUNTER, counter=ANY_COUNTER, selector=key, text=part) if key else None
    if m := _X_SELF.match(part):
        return CostComponent(REMOVE_COUNTER, amount=0, counter=m["kind"], x=True, text=part)
    if m := _PUT_SELF.match(part):
        return CostComponent(PUT_COUNTER, amount=_n(m["n"]), counter=m["kind"], text=part) if m["n"] != "another" else None
    if m := _PUT_CHOSEN.match(part):
        key = _selector(m["what"], zone="battlefield", other=m["another"] == "another")
        return CostComponent(PUT_COUNTER, amount=_n(m["n"]), counter=m["kind"], selector=key, text=part) \
            if key and m["n"] != "another" else None
    if m := _BLIGHT.match(part):  # 701.68a: put N -1/-1 counters on a creature you control
        key = _selector("creature you control", zone="battlefield")
        return CostComponent(PUT_COUNTER, amount=int(m["n"]), counter="-1/-1", selector=key, text=part) if key else None
    if m := _SAC_X.match(part):
        return _x_part(SACRIFICE, m["what"], "battlefield", part)
    if m := _TAP_X.match(part):
        return _x_part(TAP_OTHER, "untapped " + m["what"], "battlefield", part)
    if m := _EXILE_GY_X.match(part):
        return _x_part(EXILE_FROM_GRAVEYARD, m["what"], "graveyard", part)
    if part == "Discard your hand":
        return CostComponent(DISCARD_HAND, amount=0, text=part)
    if m := _MILL.match(part):
        return CostComponent(MILL, amount=_n(m["n"]) if m["n"] else 1, text=part) if m["n"] != "another" else None
    if m := _EXILE_TOP.match(part):
        return CostComponent(EXILE_LIBRARY, amount=_n(m["n"]) if m["n"] else 1, text=part) if m["n"] != "another" else None
    if (m := _EXILE_CHOSEN.match(part)) and m["n"] != "another":
        key = _selector(m["what"], zone="battlefield")
        return CostComponent(EXILE, amount=_n(m["n"]), selector=key, text=part) if key else None
    if m := _EVIDENCE.match(part):  # 701.59a
        key = _selector("cards from your graveyard", zone="graveyard")
        return CostComponent(COLLECT_EVIDENCE, amount=int(m["n"]), selector=key, text=part) if key and int(m["n"]) > 0 else None
    if part == "Forage":  # 701.61a
        return CostComponent(FORAGE, amount=3, text=part)
    if m := _SAC_OR.match(part):  # "another" belongs to its own alternative only (Mold Folk; Malevolent Noble)
        first = _selector(m["w1"], zone="battlefield", other=m["a"] == "another")
        second = _selector(m["w2"], zone="battlefield", other=m["b"] == "another")
        return CostComponent(SACRIFICE, selector=first, alt=second, text=part) if first and second else None
    if part == "Exert ~":  # 701.43a: it won't untap during your next untap step (engine.start_next_turn)
        return CostComponent(EXERT, text=part)
    if _GRANDEUR.match(part):
        key = _selector("card", zone="hand", other=True)
        return CostComponent(DISCARD, selector=key, named_self=True, text=part) if key else None
    if part == _HALF_LIFE:
        return CostComponent(PAY_LIFE, amount=0, life_rule="half", text=part)
    if part == _COMMANDER_LIFE:
        return CostComponent(PAY_LIFE, amount=0, life_rule="commander_colors", text=part)
    return None


def wave4h_parts(part: str, card_name: str) -> list[CostComponent] | None:
    """The part as one or more components (two joined by "and": the second keeps the first's verb when it has none,
    "it" being the source), or None when any piece isn't read."""
    one = _one_4h(part, card_name)
    if one is not None:
        return [one]
    pieces = _AND.split(part)
    verb = _VERB.match(part)
    if len(pieces) != 2 or verb is None:
        return None
    second = pieces[1]
    if _VERB.match(second[:1].upper() + second[1:]) is None:
        second = f"{verb['verb']} {second}"
    out: list[CostComponent] = []
    for piece in (pieces[0], second[:1].upper() + second[1:]):
        found = _component(piece, card_name) or _one_4h(piece, card_name)
        if found is None:
            return None
        out.append(found)
    return out
# -- end activation costs (wave 4H) --


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
    life_x = False
    for ab in abilities:
        text = additional_cost_text(ab.text) if ab.kind != "keywords" else None
        found = parse_additional_cost(text) if text is not None else None
        if found is not None:
            parts += found.components
            life_x = life_x or found.life_x
    if life_x:  # (wave 4K: "pay X life" alone)
        return AbilityCost(components=tuple(parts), life=sum(c.amount for c in parts if c.kind == PAY_LIFE), life_x=True)
    return AbilityCost(components=tuple(parts), life=sum(c.amount for c in parts if c.kind == PAY_LIFE)) if parts else None


def parse_additional_cost(text: str) -> AbilityCost | None:
    """The parts of a spell's additional cost ("sacrifice a creature", "discard a card and pay 2 life",
    "exile a creature card from your graveyard") as an :class:`AbilityCost` (components only), or None
    when the engine can't pay it by itself ("you may …", "… or …" alternatives, X, a cost with no
    chosen object): the spell then stays manual rather than being cast without its cost (601.2b)."""
    text = text.strip()
    if text == "pay X life":  # -- X sized by a count (wave 4K) -- Toxic Deluge: X announced as it's cast (601.2b,
        return AbilityCost(life_x=True)  # 107.3a), paid with the rest (601.2h), at most your life (119.4, 118.3)
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
