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
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from app.rules import selectors

if TYPE_CHECKING:
    from app.rules.oracle import AbilityText

# 107.4: mana symbols, including multi-digit generic mana ({10}, {12}) and hybrid / Phyrexian
# ({S} snow mana: wave 7E, app/rules/mana.py SNOW).
_MANA_ONLY = re.compile(r"^(\{(?:\d+|[WUBRGCXS]|[WUBRG2]/[WUBRGP]|[WUBRG]/[WUBRG]/P)\})+$")
_SELF = r"(?:this \w+|it|~)"
_SAC_SELF = re.compile(r"^Sacrifice (this \w+|it|~|(?P<name>.+))$")
_GRANTER_COST = re.compile(rf"^(?P<verb>Sacrifice|Unattach|Tap) (?P<g>{selectors.GRANTER})$")  # (wave 18F) the object a quoted grant came from
_LIFE = re.compile(r"^Pay (?P<n>\d+) life$")
_ENERGY = re.compile(r"^Pay (?:(?P<symbols>(?:\{E\})+)|(?P<n>\w+) \{E\})$")
_REMOVE = re.compile(
    r"^Remove (?P<n>a|an|one|two|three|four|five|six|seven|eight|\d+) (?P<kind>[\w+/\-]+) counters? from (this \w+|it|~|(?P<name>.+))$"
)
_REMOVE_ALL = re.compile(rf"^Remove all (?P<kind>[\w+/\-]+) counters from {_SELF}$")  # (the source's own: ~ / this permanent)
_N = r"(?P<n>a|an|another|one|two|three|four|five|six|seven|eight|nine|ten|thirteen|fifteen|\d+)"  # (seven …: wave 4H; fifteen: 17B)
_SAC_CHOSEN = re.compile(rf"^Sacrifice {_N} (?P<what>.+)$")
_DISCARD = re.compile(rf"^Discard {_N} (?P<what>(?:[\w\-]+ )*cards?)(?P<random> at random)?$")
_DISCARD_SELF = re.compile(r"^Discard (?:this card|~)$")  # -- ability words (wave 4F) -- channel (113.6m)
_REVEAL_SELF = re.compile(r"^Reveal (?:this (?:card|creature)|~) from your hand$")  # -- forecast (wave 24C) -- 702.57a (113.6m: from the hand)
REVEAL_SELF = "REVEAL_SELF"
_EXILE_SELF_GY = re.compile(rf"^Exile {_SELF} from your graveyard$")
_EXILE_SELF_HAND = re.compile(r"^Exile (?:this card|~) from your hand$")  # -- as long as (wave 37A) -- "{2}, Exile this card from your hand: …" (113.6m: works only from the hand)
_EXILE_SELF = re.compile(rf"^Exile {_SELF}$")
_EXILE_GY = re.compile(rf"^Exile {_N} (?P<what>(?:[\w\-]+ )*cards? from your graveyard)$")
_RETURN_SELF = re.compile(rf"^Return {_SELF} to its owner's hand$")
_RETURN = re.compile(rf"^Return {_N} (?P<what>.+? you control) to (?:its|their) owner's hands?$")
# -- X sized by a count (wave 25D) -- a spell's additional cost sized by the X announced as it's cast (107.3a, 601.2b): "discard X cards",
# "return X Swamps you control to their owner's hand" (the sacrifice / exile ones are ``_SAC_X`` / ``_EXILE_GY_X``)
_DISCARD_X = re.compile(r"^Discard X (?P<what>(?:[\w\-]+ )*cards?)(?P<random> at random)?$")
_RETURN_X = re.compile(r"^Return X (?P<what>.+? you control) to (?:its|their) owner's hands?$")
_TAP_OTHER = re.compile(rf"^Tap {_N} (?P<another>another )?untapped (?P<what>.+ you control(?: other than (?:~|this creature))?)$")
_UNTAP_OTHER = re.compile(rf"^Untap {_N} tapped (?P<what>.+ you control)$")  # -- activated sweep (wave 17B) -- Halo Fountain
_REMOVE_CHOSEN = re.compile(
    r"^Remove (?P<n>a|an|one|two|three|\d+) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? from (?:a|an|another) (?P<what>.+)$")
_WORDS = {"a": 1, "an": 1, "another": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
          "seven": 7, "eight": 8, "nine": 9, "ten": 10, "thirteen": 13, "fifteen": 15}  # (seven …: wave 4H, "Exile seven cards from your graveyard")
_ENERGY_WORDS = {**_WORDS, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "fifty": 50}  # (wave 3E: "Pay eight {E}")

# Component kinds (the parts of a cost, 118.1)
MANA, TAP, UNTAP, SACRIFICE, DISCARD, PAY_LIFE, PAY_ENERGY = "MANA", "TAP", "UNTAP", "SACRIFICE", "DISCARD", "PAY_LIFE", "PAY_ENERGY"
EXILE, EXILE_FROM_GRAVEYARD, REMOVE_COUNTER, RETURN_PERMANENT = "EXILE", "EXILE_FROM_GRAVEYARD", "REMOVE_COUNTER", "RETURN_PERMANENT"
TAP_OTHER, REVEAL, LOYALTY, OTHER = "TAP_OTHER", "REVEAL", "LOYALTY", "OTHER"
UNTAP_OTHER = "UNTAP_OTHER"  # -- activated sweep (wave 17B) -- "Untap two tapped creatures you control" (the payer picks, 701.26a)
# -- activation costs (wave 4H) -- put counters (122.6; blight 701.68a), discard your hand, mill (701.17), exile from the
# top of your library, exert the source (701.43a); ANY_COUNTER: "Remove a counter from …" (the payer picks the kind)
PUT_COUNTER, DISCARD_HAND, MILL, EXILE_LIBRARY, EXERT = "PUT_COUNTER", "DISCARD_HAND", "MILL", "EXILE_LIBRARY", "EXERT"
COLLECT_EVIDENCE, FORAGE = "COLLECT_EVIDENCE", "FORAGE"  # 701.59a, 701.61a: the payer picks how many / which way
# -- if you do (wave 15C) -- the Eldrazi processors: "Put a card an opponent owns from exile into that player's graveyard"
# (a cost like any other: 118.1; the cards are chosen from the exile zones of the opponents and go to their owners', 400.3)
EXILE_TO_GY = "EXILE_TO_GY"
# -- activated sweep (wave 17B) -- "Waterbend {3}" (701.67a): {3}, and for each generic mana in it the payer may tap an untapped artifact
# or creature they control instead of paying that mana; the cost is the MANA part plus this one, which holds how many may be tapped
WATERBEND = "WATERBEND"
# -- casting extras (wave 18E) -- craft (702.167a): "Exile [materials] from among permanents you control and/or cards in your graveyard",
# one part for each description; ``selector`` the permanents it may take, ``alt`` the graveyard cards, ``amount`` how many ("or more": ``more``)
CRAFT = "CRAFT"
# -- granted from object (wave 18F) -- "Unattach Heartseeker" (701.3d): the granting Equipment (selectors.GRANTER), moved away from its creature
UNATTACH = "UNATTACH"
WAVE_4H_KINDS = frozenset({PUT_COUNTER, DISCARD_HAND, MILL, EXILE_LIBRARY, EXERT, COLLECT_EVIDENCE, FORAGE, WATERBEND, CRAFT, UNATTACH})
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
    more: bool = False  # -- casting extras (wave 18E) -- "N or more" (craft materials)
    up_to: bool = False  # -- casting extras (wave 18E) -- "up to N" (harmonize 702.180a: "tapping up to one untapped creature"): none is a choice
    every: bool = False  # -- activated sweep (wave 26C) -- "Remove all oil counters from ~": X is every such counter there is, set as it's activated
    among: bool = False  # -- activated sweep (wave 26C) -- "Remove two +1/+1 counters from among creatures you control": any permanents, one pick per counter

    @property
    def chosen(self) -> bool:
        """Does paying it need a choice of objects (casting.cost_choices)?"""
        return (self.selector is not None and not self.random) or self.counter == ANY_COUNTER \
            or self.kind in (COLLECT_EVIDENCE, FORAGE, CRAFT)  # (wave 4H; craft: 18E)

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
        return self.kind in WAVE_4H_KINDS or (self.x and self.kind != PAY_ENERGY) or self.counter == ANY_COUNTER or self.among \
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
    hand_only: bool = False  # -- activated from hand / command zone (wave 27D) -- its effect moves this card out of your hand (113.6m)
    command_only: bool = False  # (…or out of the command zone)
    life_x: bool = False  # -- X sized by a count (wave 4K) -- a spell's "pay X life" (107.3a: X announced as it's cast)
    # -- static wordings (wave 6E) -- "As an additional cost to cast this spell, discard a card or pay 3 life.": the
    # costs to choose between (601.2b), each a cost of its own (a mana one: ``mana`` only); no components of its own
    either: tuple[AbilityCost, ...] = ()

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
        return any(c.x and not c.every for c in self.components)

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
        return self.hand_only or any((c.kind in (DISCARD, "EXILE_FROM_HAND") and c.selector is None) or c.kind == REVEAL_SELF  # (EXILE_FROM_HAND: wave 37A)
                                     for c in self.components)

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
    if phrase in ("token", "tokens"):
        phrase = "token permanent"
    sel = selectors.parse(phrase)
    if sel is None or sel.player is not None or sel.extras and any(
            e in ("enchanted", "equipped") for e in sel.extras) or (sel.attacking and "unblocked" not in sel.extras) or sel.blocking:
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
    if m := _GRANTER_COST.match(part):  # -- granted from object (wave 18F) -- paid with that object (601.2h): the one choice, made for you
        sel = selectors.parse(m["g"])
        assert sel is not None
        if m["verb"] == "Tap":  # (an untapped one: 118.3)
            return CostComponent(TAP_OTHER, selector=replace(sel, tapped=False).key(), text=part)
        return CostComponent(SACRIFICE if m["verb"] == "Sacrifice" else UNATTACH, selector=sel.key(), text=part)
    if (m := _SAC_SELF.match(part)) and (not m.group("name") or m.group("name") == card_name):
        return CostComponent(SACRIFICE, text=part)
    if m := _LIFE.match(part):
        return CostComponent(PAY_LIFE, amount=int(m["n"]), text=part)
    if m := _ENERGY.match(part):
        if m["n"] == "X":  # -- counters & designations (wave 3E) -- "Pay X {E}" (X chosen as it's activated)
            return CostComponent(PAY_ENERGY, amount=0, x=True, text=part)
        n = m["symbols"].count("{E}") if m["symbols"] else _ENERGY_WORDS.get(m["n"].lower()) or (int(m["n"]) if m["n"].isdigit() else 0)
        return CostComponent(PAY_ENERGY, amount=n, text=part) if n else None
    if m := _REMOVE_ALL.match(part):  # -- activated sweep (wave 26C) -- 602.2b: not announced, it's all of them (casting sets X to that many)
        return CostComponent(REMOVE_COUNTER, amount=0, counter=m["kind"], x=True, every=True, text=part)
    if (m := _REMOVE.match(part)) and (not m.group("name") or m.group("name") == card_name):
        return CostComponent(REMOVE_COUNTER, amount=_n(m["n"]), counter=m["kind"], text=part)
    if _EXILE_SELF_GY.match(part):
        return CostComponent(EXILE_FROM_GRAVEYARD, text=part)
    if _EXILE_SELF_HAND.match(part):  # -- as long as (wave 37A) -- the source itself, exiled from the hand as the cost is paid (cost_payment: no selector = the source)
        return CostComponent("EXILE_FROM_HAND", text=part)
    if _DISCARD_SELF.match(part):  # -- ability words (wave 4F) -- "Discard this card" (701.9a; 113.6m: from the hand)
        return CostComponent(DISCARD, text=part)
    if _REVEAL_SELF.match(part):  # -- forecast (wave 24C) -- revealed to everyone (701.20a), the card stays in the hand
        return CostComponent(REVEAL_SELF, text=part)
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
        what, other = re.subn(r" other than (?:~|this creature)$", "", m["what"])  # (wave 26C: "Tap an untapped red creature you control other than ~")
        key = _selector("untapped " + what, zone="battlefield", other=bool(m["another"]) or m["n"] == "another" or bool(other))
        return CostComponent(TAP_OTHER, amount=_n(m["n"]), selector=key, text=part) if key else None
    if m := _UNTAP_OTHER.match(part):
        key = _selector("tapped " + m["what"], zone="battlefield")
        return CostComponent(UNTAP_OTHER, amount=_n(m["n"]), selector=key, text=part) if key else None
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
    # -- tutor (wave 26D) -- "Sacrifice a red creature, a green creature, and a white creature" (the Heralds): one part, three objects
    cost = re.sub(r"(Sacrifice (?:an?|another) [^,{}:]+?), ((?:an?|another) [^,{}:]+?), and ((?:an?|another) [^,{}:]+?)(?=,|$)",
                  r"\1 and \2 and \3", cost)
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
    if any(c.every for c in components) and (sum(c.every for c in components) > 1 or any(
            (c.x and not c.every) or (c.kind == MANA and "X" in c.text) for c in components)):
        unsupported.append(cost)  # (wave 26C: the one X is the counters removed; a second X would be the same number)
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
_AMONG = re.compile(r"^Remove (?P<n>a|one|two|three|four|five|X) (?:(?P<kind>\+1/\+1|-1/-1|[a-z]+) )?counters? from among (?P<what>.+ you control)$")
_PUT_SELF = re.compile(rf"^Put {_N} (?P<kind>[\w+/\-]+) counters? on {_SELF}$")
_PUT_CHOSEN = re.compile(rf"^Put {_N} (?P<kind>[+-]\d+/[+-]\d+) counters? on (?P<another>a|an|another) (?P<what>[^,]+ you control)$")
_BLIGHT = re.compile(r"^Blight (?P<n>\d+)$")
_SAC_X = re.compile(r"^Sacrifice X (?P<what>.+)$")
_TAP_X = re.compile(r"^Tap X untapped (?P<what>.+ you control)$")
_EXILE_GY_X = re.compile(r"^Exile X (?P<what>(?:[\w\-]+ )*cards from your graveyard)$")
_MILL = re.compile(rf"^Mill (?:a card|{_N} cards)$")
_EXILE_TOP = re.compile(rf"^Exile the top (?:card|{_N} cards) of your library$")
_EXILE_CHOSEN = re.compile(rf"^Exile {_N} (?P<what>[^,]+ you control)$")
_EXILE_TO_GY = re.compile(r"^Put (?:(?P<one>a) card an opponent owns from exile into that player's graveyard"
                          r"|(?P<n>two|three) cards your opponents own from exile into their owners' graveyards)$")  # (wave 15C)
_EVIDENCE = re.compile(r"^Collect evidence (?P<n>\d+)$")
# "Exile an artifact from among permanents you control and/or cards in your graveyard" / "…two creatures…" / "…one or more Dinosaurs…"
_CRAFT = re.compile(r"^Exile (?P<n>a|an|one|two|three|four|five|six|seven|\d+)(?P<more> or more)?(?: (?P<what>[^,]+?))? from among "
                    r"permanents you control and/or cards in your graveyard$")
_WATERBEND = re.compile(r"^Waterbend \{(?P<n>\d+)\}$")
_SAC_OR = re.compile(r"^Sacrifice (?P<a>a|an|another) (?P<w1>[\w\-]+) or (?P<b>a|an|another) (?P<w2>[\w\-]+)$")  # (no article: refused)
_GRANDEUR = re.compile(r"^Discard another card named ~$")  # (grandeur, an ability word: 207.2c)
_HALF_LIFE = "Pay half your life rounded up"
_COMMANDER_LIFE = "Pay life equal to the number of colors in your commanders' color identity"
_AND = re.compile(r" and (?=(?:(?:sacrifice|exile|return|remove|discard|tap|put|pay) )?(?:(?:a|an|another|one|two|three|four|five|six|seven|eight|nine|ten|thirteen|fifteen|this|it|\d+)\b|~))")  # (wave 34B: any count word the cost reads, Glass-Cast Heart)
_VERB = re.compile(r"^(?P<verb>Sacrifice|Exile|Return|Remove|Discard|Tap|Put|Pay) ")


def _x_part(kind: str, what: str, zone: str, text: str) -> CostComponent | None:
    key = _selector(what, zone=zone)
    return CostComponent(kind, amount=0, selector=key, x=True, text=text) if key else None


def _exile_to_gy(part: str) -> CostComponent | None:
    """-- if you do (wave 15C) -- the processors' cost; only cards a player can look at: face-up exile (406.3)."""
    from app.rules import selectors

    m = _EXILE_TO_GY.match(part)
    if m is None:
        return None
    key = selectors.Selector(card=True, zones=("exile",), zone_owner="opponent").key()
    return CostComponent(EXILE_TO_GY, amount=1 if m["one"] else _n(m["n"]), selector=key, text=part)


def _craft_part(m: re.Match[str], part: str) -> CostComponent | None:
    """-- casting extras (wave 18E) -- 702.167a-b: a material described by a card type or subtype alone is a permanent you control or a
    card in your graveyard of that type; with the word "card" (109.2) only a graveyard card. "one or more" alone: any object."""
    what = re.sub(r"\b(\w+?)s\b$", r"\1", m["what"] or "", count=1) if m["what"] and not m["what"].endswith("Merfolk") else m["what"] or ""
    n = _n(m["n"]) if m["n"].isdigit() or m["n"] in _WORDS else None
    if n is None or " with " in what or what.endswith("nonland") or "share" in what:
        return None  # (conditions on the objects, "that share a card type": not read)
    if not what:
        perm, grave = _selector("permanent you control", zone="battlefield"), _selector("card from your graveyard", zone="graveyard")
    elif what.endswith(" card") or what == "card":
        perm, grave = None, _selector(what + " from your graveyard", zone="graveyard")
    else:
        perm, grave = _selector(what + " you control", zone="battlefield"), _selector(what + " card from your graveyard", zone="graveyard")
    if (perm is None and grave is None) or (not what.endswith(" card") and what != "card" and (perm is None or grave is None)):
        return None
    return CostComponent(CRAFT, amount=n, selector=perm, alt=grave, more=bool(m["more"]), text=part)


def _one_4h(part: str, card_name: str) -> CostComponent | None:
    """One more part (the list above), or None."""
    if m := _ANY_SELF.match(part):
        return CostComponent(REMOVE_COUNTER, amount=_n(m["n"]), counter=ANY_COUNTER, text=part)
    if m := _ANY_CHOSEN.match(part):
        key = _selector(m["what"], zone="battlefield", other=m["another"] == "another")
        return CostComponent(REMOVE_COUNTER, counter=ANY_COUNTER, selector=key, text=part) if key else None
    if m := _X_SELF.match(part):
        return CostComponent(REMOVE_COUNTER, amount=0, counter=m["kind"], x=True, text=part)
    if m := _AMONG.match(part):  # -- activated sweep (wave 26C) -- 122.1: the counters come off any of the permanents, one pick for each counter
        key = _selector(m["what"], zone="battlefield")
        if key is None or m["what"].startswith("other "):
            return None
        return CostComponent(REMOVE_COUNTER, amount=0 if m["n"] == "X" else _n(m["n"]), counter=m["kind"] or ANY_COUNTER, selector=key,
                             x=m["n"] == "X", among=True, text=part)
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
    if m := _DISCARD_X.match(part):  # -- X sized by a count (wave 25D) -- 701.9a: X cards of your choice (at random: the engine picks)
        key = _selector(m["what"], zone="hand")
        return CostComponent(DISCARD, amount=0, selector=key, x=True, random=bool(m["random"]), text=part) if key else None
    if m := _RETURN_X.match(part):
        return _x_part(RETURN_PERMANENT, m["what"], "battlefield", part)
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
    if m := _EXILE_CHOSEN.match(part):  # (-- champion (wave 12B) -- "another": not the source itself)
        key = _selector(m["what"], zone="battlefield", other=m["n"] == "another")
        return CostComponent(EXILE, amount=_n(m["n"]), selector=key, text=part) if key else None
    if (processed := _exile_to_gy(part)) is not None:  # (wave 15C)
        return processed
    if m := _CRAFT.match(part):  # -- casting extras (wave 18E) -- 702.167a / 702.167b
        return _craft_part(m, part)
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
    if m := _WATERBEND.match(part):  # -- activated sweep (wave 17B) -- 701.67a (only a number: "Waterbend {X}" is not read)
        key = _selector("untapped artifact or creature you control", zone="battlefield")
        return [CostComponent(MANA, text=f"{{{m['n']}}}"),
                CostComponent(WATERBEND, amount=int(m["n"]), selector=key, text=part)] if key and int(m["n"]) > 0 else None
    one = _one_4h(part, card_name)
    if one is not None:
        return [one]
    pieces = _AND.split(part)
    verb = _VERB.match(part)
    if not 2 <= len(pieces) <= 3 or verb is None or (len(pieces) == 3 and verb["verb"] != "Sacrifice"):  # (wave 26D: three sacrifices, the Heralds)
        return None
    rest = [r[:1].upper() + r[1:] if _VERB.match(r[:1].upper() + r[1:]) else f"{verb['verb']} {r}" for r in pieces[1:]]
    out: list[CostComponent] = []
    for piece in (pieces[0], *rest):
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
# -- keywords (wave 15E) -- squad (702.157: "you may pay [cost] any number of times"), replicate (702.56: the same) and offspring
# (702.175: once) are optional additional mana costs paid as kicker is (``CastSpell.kicker`` times): the engine's count is theirs
_KICKER = re.compile(r"^(?:(?P<multi>multi)?kicker|(?P<many>squad|replicate)|(?P<once>offspring)|(?P<entwine>entwine)) (?P<cost>(?:\{[^}]+\})+)$",
                     re.IGNORECASE)


# -- casting extras (wave 18E) -- 702.42a: an entwine cost that isn't mana ("Entwine—Sacrifice three lands.") is paid as additional costs are
_ENTWINE_EXTRA = re.compile(r"^entwine—(?P<rest>[^{}.]+)$", re.IGNORECASE)


def _entwine_extra(line: str) -> str | None:
    """The non-mana entwine cost of a line the engine pays ("sacrifice two lands"), or None."""
    from app.rules import alt_costs

    m = _ENTWINE_EXTRA.fullmatch(re.sub(r"\s*\(.*?\)", "", line).strip().rstrip("."))
    return m["rest"].strip() if m is not None and alt_costs.parse_cost(m["rest"].strip()) is not None else None


def kicker_line(line: str) -> bool:
    """Is this keyword line a kicker the engine pays ("Kicker {2}{R}", "Multikicker {1}")?"""
    if _entwine_extra(line) is not None:
        return True
    m = _KICKER.fullmatch(line.strip().rstrip("."))
    return m is not None and "{X}" not in m["cost"].upper() and _MANA_ONLY.match(m["cost"]) is not None


@dataclass(frozen=True)
class Kicker:
    cost: str  # mana symbols, e.g. "{2}{R}"
    multi: bool = False  # 702.33c multikicker: any number of times
    entwine: bool = False  # -- casting extras (wave 18E) -- 702.42a: the count 1 means "choose all modes" (paid as kicker is)
    extra: str = ""  # (an entwine cost that isn't mana: "sacrifice two lands", paid with the additional costs)


def kicker_cost(abilities: Iterable[AbilityText]) -> Kicker | None:
    """702.33a / 702.33c: the card's "Kicker {cost}" or "Multikicker {cost}" line (mana only), or
    None. Two kicker costs ("Kicker {1}{U} and/or {2}{B}", 702.33b), non-mana kicker costs
    ("Kicker—Sacrifice a land") and X in the cost stay manual."""
    found: list[Kicker] = []
    for ab in abilities:
        if ab.kind != "keywords" or not ({"kicker", "multikicker", "squad", "replicate", "offspring", "entwine"} & set(ab.keywords)):
            continue
        if (extra := _entwine_extra(ab.text)) is not None:
            found.append(Kicker("", entwine=True, extra=extra))
            continue
        m = _KICKER.fullmatch(ab.text.strip().rstrip("."))
        if m is None or not kicker_line(ab.text):
            return None
        found.append(Kicker(m["cost"], multi=bool(m["multi"] or m["many"]), entwine=bool(m["entwine"])))
    return found[0] if len(found) == 1 else None


# -- costs (wave 3$) -- additional costs to cast a spell (118.8, 601.2b) ----------------------------------
_ADDITIONAL = re.compile(r"^as an additional cost to cast (?:this spell|~), (?P<cost>[^.]+)\.?$", re.IGNORECASE)
# What a spell's additional cost may be made of: parts with chosen objects (or life / energy). Never the
# source itself (a spell isn't on the battlefield to be sacrificed), tapping it, mana or counters on it.
# -- static_other sweep (wave 17C) -- also "reveal a Merfolk card from your hand" (REVEAL_FROM_HAND, as optional_payment reads it),
# "behold an Elf" (701.4a: reveal an Elf card from your hand or choose an Elf you control), "blight 1" (701.68a), "forage" (701.61a)
# and "exile a creature you control": the parts of an activation cost cost_payment already pays
BEHOLD = "BEHOLD"
_ADDITIONAL_KINDS = frozenset({SACRIFICE, DISCARD, PAY_LIFE, PAY_ENERGY, EXILE_FROM_GRAVEYARD, RETURN_PERMANENT, TAP_OTHER,
                               EXILE_TO_GY,  # (EXILE_TO_GY: wave 15C)
                               "REVEAL_FROM_HAND", BEHOLD, PUT_COUNTER, FORAGE, EXILE})
_REVEAL_HAND_COST = re.compile(r"^Reveal (?:a|an) (?P<what>.+? card) from your hand$")
_BEHOLD_COST = re.compile(r"^Behold (?:a|an) (?P<q>[A-Z][a-z]+)$")


def _extra_part(part: str) -> CostComponent | None:
    """-- static_other sweep (wave 17C) -- one of the parts above that a spell's additional cost may also be made of."""
    if m := _REVEAL_HAND_COST.match(part):
        key = _selector(m["what"], zone="hand")
        return CostComponent("REVEAL_FROM_HAND", selector=key, text=part) if key else None
    if m := _BEHOLD_COST.match(part):
        hand, field = _selector(f"{m['q']} card", zone="hand"), _selector(f"{m['q']} you control", zone="battlefield")
        return CostComponent(BEHOLD, selector=hand, alt=field, text=part) if hand and field else None
    found = _one_4h(part, "")
    if found is not None and (found.kind == FORAGE or (found.kind == PUT_COUNTER and part.startswith("Blight"))
                              or (found.kind == EXILE and found.selector is not None and not found.x)):
        return found
    return None


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
    either: list[AbilityCost] = []
    for ab in abilities:
        text = additional_cost_text(ab.text) if ab.kind != "keywords" else None
        found = parse_additional_cost(text) if text is not None else None
        if found is not None and found.either:  # -- static wordings (wave 6E) --
            if either or life_x:
                return AbilityCost(unsupported=(text or "",))  # (two choices of cost: never cast without them)
            either = list(found.either)
        elif found is not None:
            parts += found.components
            life_x = life_x or found.life_x
    if either:  # -- static wordings (wave 6E) -- the fixed parts are paid with whichever is chosen (601.2f)
        if life_x:
            return AbilityCost(unsupported=("pay X life",))
        branches = tuple(AbilityCost(mana=b.mana, components=b.components + tuple(parts),
                                     life=sum(c.amount for c in b.components + tuple(parts) if c.kind == PAY_LIFE))
                         for b in either)
        return AbilityCost(either=branches)
    if life_x:  # (wave 4K: "pay X life" alone)
        return AbilityCost(components=tuple(parts), life=sum(c.amount for c in parts if c.kind == PAY_LIFE), life_x=True)
    return AbilityCost(components=tuple(parts), life=sum(c.amount for c in parts if c.kind == PAY_LIFE)) if parts else None


def parse_additional_cost(text: str) -> AbilityCost | None:
    """The parts of a spell's additional cost ("sacrifice a creature", "discard a card and pay 2 life",
    "exile a creature card from your graveyard") as an :class:`AbilityCost` (components only), or None
    when the engine can't pay it by itself ("you may …", "… or …" alternatives, X, a cost with no
    chosen object): the spell then stays manual rather than being cast without its cost (601.2b)."""
    text = text.strip()
    either = _either(text)  # -- static wordings (wave 6E) --
    if either is not None:
        return either if either.either else None
    if text == "pay X life":  # -- X sized by a count (wave 4K) -- Toxic Deluge: X announced as it's cast (601.2b,
        return AbilityCost(life_x=True)  # 107.3a), paid with the rest (601.2h), at most your life (119.4, 118.3)
    text = re.sub(r"\b(\w+), (\w+), and/or (\w+)\b", r"\1 or \2 or \3", text)  # (wave 17C: "tap two untapped artifacts, creatures, and/or lands")
    if text.lower().startswith("you may") or "," in text:
        return None
    has_x = re.search(r"\bx\b", text, re.IGNORECASE) is not None  # -- X sized by a count (wave 25D) -- one part sized by the announced X (below)
    if has_x and not re.match(r"^(?:sacrifice|discard|exile|return) X ", text, re.IGNORECASE):
        return None
    parts = [p.strip() for p in re.split(r" and (?=(?:sacrifice|discard|pay|exile|return|tap) )", text)]
    components: list[CostComponent] = []
    for part in parts:
        found = _component(part[:1].upper() + part[1:], "") or _exile_to_gy(part[:1].upper() + part[1:]) \
            or _extra_part(part[:1].upper() + part[1:])
        if found is None and has_x:  # (the part sized by X, 107.3a: one only — "discard X cards and sacrifice X creatures" isn't read)
            found = _one_4h(part[:1].upper() + part[1:], "")
            if found is None or not found.x or len(parts) != 1:
                return None
        if found is None or found.kind not in _ADDITIONAL_KINDS:
            return None
        if found.selector is None and found.kind not in (PAY_LIFE, PAY_ENERGY, FORAGE):
            return None
        components.append(found)
    return AbilityCost(components=tuple(components), life=sum(c.amount for c in components if c.kind == PAY_LIFE))


# -- static wordings (wave 6E) -- a choice between additional costs (601.2b: announced as the spell is cast; 601.2f: the
# chosen one is part of the total cost): "sacrifice an artifact or discard a card", "discard a card or pay 3 life",
# "sacrifice a creature or pay {3}{B}" (a mana branch is paid with the mana cost). Each side must be a cost the grammar
# pays by itself; "reveal …", "behold …", "blight …", "forage" sides stay manual.
_EITHER_SPLIT = re.compile(r" or (?=(?:sacrifice|discard|pay|exile|return|tap) )")
_PAY_MANA = re.compile(r"^pay (?P<mana>(?:\{(?:\d+|[WUBRGC]|[WUBRG2]/[WUBRGP])\})+)$")
EITHER_SLOT = 20  # (the cost choice that names the chosen side: "either:<i>", A.CostChoice.component's last index)


def _either(text: str) -> AbilityCost | None:
    """None: not a choice; AbilityCost(either=()) a choice the grammar can't pay; else the sides."""
    sides = _EITHER_SPLIT.split(text)
    if len(sides) < 2:
        return None
    out: list[AbilityCost] = []
    for side in sides:
        m = _PAY_MANA.match(side.strip())
        if m is not None:
            out.append(AbilityCost(mana=m["mana"]))
            continue
        found = parse_additional_cost(side)
        if found is None or found.either or found.life_x or found.unsupported or found.x_chosen:  # (wave 25D: an X-sized side isn't read)
            return AbilityCost()
        out.append(found)
    return AbilityCost(either=tuple(out))


def either_label(cost: AbilityCost) -> str:
    """How one side of a choice reads ("Pay {3}", "Sacrifice a creature and pay 2 life")."""
    if cost.mana and not cost.components:
        return f"Pay {cost.mana}"
    text = " and ".join(c.text for c in cost.components)
    return (text[:1].upper() + text[1:]) if text else "No additional cost"
