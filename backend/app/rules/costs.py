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
from typing import TYPE_CHECKING, Literal

from app.rules import selectors
from app.rules.mana_requirement_rows import RequirementPlan

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
    r"^Remove (?P<n>a|an|one|two|three|four|five|six|seven|eight|fifty|\d+) (?P<kind>[\w+/\-]+) counters? from (this \w+|it|~|(?P<name>.+))$"
)
_REMOVE_ALL = re.compile(rf"^Remove all (?P<kind>[\w+/\-]+) counters from {_SELF}$")  # (the source's own: ~ / this permanent)
_N = r"(?P<n>a|an|another|one|two|three|four|five|six|seven|eight|nine|ten|thirteen|fifteen|\d+)"  # (seven …: wave 4H; fifteen: 17B)
_SAC_CHOSEN = re.compile(rf"^Sacrifice {_N} (?P<what>.+)$")
_COST_CARD = r"(?:[\w\-]+ )*cards?(?: with (?:mana value X|flying))?"  # (wave 110F: "a creature card with flying", Steamcore Scholar)
_DISCARD = re.compile(rf"^Discard {_N} (?P<what>{_COST_CARD})(?P<random> at random)?$")
_DISCARD_SELF = re.compile(r"^Discard (?:this card|~)$")  # -- ability words (wave 4F) -- channel (113.6m)
_REVEAL_SELF = re.compile(r"^Reveal (?:this (?:card|creature)|~) from your hand$")  # -- forecast (wave 24C) -- 702.57a (113.6m: from the hand)
REVEAL_SELF = "REVEAL_SELF"
REVEAL_HAND = "REVEAL_HAND"
# -- group choices (wave 53D) -- "Reveal the player you chose" (Stalking Leonin), "Reveal the creature type you chose" (A Killer Among Us): the secret choice its controller made as it entered
# is shown as the cost is paid (cost_payment); without one (it came under your control, or a copy of it) the cost can't be paid
_REVEAL_SECRET = re.compile(r"^Reveal the (?:player|creature type) you chose$")
REVEAL_SECRET = "REVEAL_SECRET"
_EXILE_SELF_GY = re.compile(rf"^Exile {_SELF} from your graveyard$")
_EXILE_SELF_HAND = re.compile(r"^Exile (?:this card|~) from your hand$")  # -- as long as (wave 37A) -- "{2}, Exile this card from your hand: …" (113.6m: works only from the hand)
_EXILE_SELF = re.compile(rf"^Exile {_SELF}$")
_EXILE_GY = re.compile(rf"^Exile {_N} (?P<what>{_COST_CARD} from your graveyard)$")
_RETURN_SELF = re.compile(rf"^Return {_SELF} to its owner's hand$")
_BOTTOM_SELF = re.compile(rf"^Put {_SELF} on the bottom of its owner's library$")  # -- activated (wave 100I) -- (Timestream Navigator)
_RETURN = re.compile(rf"^Return {_N} (?P<what>.+? you control) to (?:its|their) owner's hands?$")
# -- X sized by a count (wave 25D) -- a spell's additional cost sized by the X announced as it's cast (107.3a, 601.2b): "discard X cards",
# "return X Swamps you control to their owner's hand" (the sacrifice / exile ones are ``_SAC_X`` / ``_EXILE_GY_X``)
_DISCARD_X = re.compile(r"^Discard X (?P<what>(?:[\w\-]+ )*cards?)(?P<random> at random)?$")
_RETURN_X = re.compile(r"^Return X (?P<what>.+? you control) to (?:its|their) owner's hands?$")
# -- static_other (wave 36B) -- "Tap two other untapped Halflings you control" (Saradoc, Spring-Loaded Sawblades): "other" than the source, as "another"
_TAP_OTHER = re.compile(rf"^Tap {_N} (?P<another>another |other )?untapped (?P<what>.+ you control(?: with [a-z ]+?)?(?: other than (?:~|this creature))?)$")  # (wave 48C: Radiant, "… you control with flying")
# -- attached events (wave 40B) -- 303.4b, 301.5: "Tap enchanted land: …" (Earthlore), "Sacrifice enchanted creature: …" (Betrothed of Fire): the permanent the source
# is attached to (selectors "host_of_source"), paid with it as the one choice, made for you
_HOST_COST = re.compile(r"^(?P<verb>Tap|Sacrifice) (?:enchanted (?:creature|land|permanent|artifact)|equipped creature)$")  # (artifact: wave 100A, Curse Artifact)
_UNTAP_OTHER = re.compile(rf"^Untap {_N} tapped (?P<what>.+ you control)$")  # -- activated sweep (wave 17B) -- Halo Fountain
_REMOVE_CHOSEN = re.compile(
    r"^Remove (?P<n>a|an|one|two|three|\d+) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? from (?:a|an|another) (?P<what>.+)$")
_WORDS = {"a": 1, "an": 1, "another": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
          "seven": 7, "eight": 8, "nine": 9, "ten": 10, "thirteen": 13, "fifteen": 15, "fifty": 50}  # (seven …: wave 4H, "Exile seven cards from your graveyard")
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
HAND_TO_TOP = 'HAND_TO_TOP'
EXILE_TOP_OWN_GY = 'EXILE_TOP_OWN_GY'
LIBRARY_BOTTOM_SELF = "LIBRARY_BOTTOM_SELF"  # -- activated (wave 100I) -- the source onto the bottom of its owner's library
WAVE_4H_KINDS = frozenset({EXILE_TOP_OWN_GY, HAND_TO_TOP, PUT_COUNTER, DISCARD_HAND, MILL, EXILE_LIBRARY, EXERT, COLLECT_EVIDENCE, FORAGE, WATERBEND, CRAFT, UNATTACH, REVEAL_SECRET, REVEAL_HAND,
                           LIBRARY_BOTTOM_SELF})
ANY_COUNTER = "*"
OPPONENT_GAIN_LIFE = "OPPONENT_GAIN_LIFE"


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
    targets_mv110g: bool = False  # -- wave 110G -- "collect evidence X, where X is the total mana value of the permanents this spell targets": casting.target_evidence fixes the amount
    reduces: int = 0  # -- cost reductions paid with objects (wave 47C) -- "you may sacrifice any number of creatures. This spell costs {2} less for each": any number, none too; each takes this much generic off the total cost
    anyn: bool = False  # (wave 48B: any number, none too, with or without a reduction: "sacrifice any number of creatures", "for each creature sacrificed this way")
    offering: bool = False  # -- offering (wave 51H) -- 702.48a: the sacrifice whose mana cost (colors included) takes that much off the spell's total cost (offering.reduce)
    names: str | None = None  # CR 201.2a–b: a constraint on the entire chosen payment group
    all_objects: bool = False  # Every matching controlled permanent, including an empty set.
    amount_rule: Literal["opponents"] | None = None  # Bound when the actual activation total is determined.
    gain_scope: Literal["each_other_player"] | None = None  # Nominal life-gain cost paid to every other live player.
    source_with_choices: bool = False  # One graveyard-exile instruction includes its required source and selected others.
    counter_options: tuple[str, ...] = ()  # A bounded choice of named counter kinds, not every counter.
    half: bool = False  # -- wave 110A -- 'sacrifice half the lands you control, rounded up': the count is read from the board as the cost is paid
    counters_x: bool = False  # -- blight X (wave 110C) -- 701.68a: the announced X is the number of counters put on the one creature chosen

    @property
    def chosen(self) -> bool:
        """Does paying it need a choice of objects (casting.cost_choices)?"""
        return (self.selector is not None and not self.random) or self.counter == ANY_COUNTER \
            or self.kind in (COLLECT_EVIDENCE, FORAGE, CRAFT, OPPONENT_GAIN_LIFE)  # (wave 4H; craft: 18E)

    @property
    def objects(self) -> int:
        """-- activation costs (wave 4H) -- how many objects a chosen part takes: one permanent for its counters
        ("Remove two +1/+1 counters from a creature you control", "Blight 2"), else ``amount`` (X: ``x``)."""
        return 1 if self.kind in (REMOVE_COUNTER, PUT_COUNTER, OPPONENT_GAIN_LIFE) else self.amount

    @property
    def selector_x(self) -> bool:
        """107.3a: an activation-cost card's mana value can be the announced X."""
        return any(key and key.startswith(selectors.PREFIX) and any(
            stat == "mv" and n == selectors.X_VALUE for stat, _, n in selectors.from_key(key).compare)
            for key in (self.selector, self.alt))

    @property
    def activation_only(self) -> bool:
        """-- activation costs (wave 4H) -- a part only an activated ability's activation pays (casting.activate_to_stack
        through app/rules/cost_payment.py): never a mana ability's (605: no stack, no X), an optional payment's or a
        spell's additional cost."""
        return self.amount_rule is not None or self.kind in WAVE_4H_KINDS or self.names is not None or self.selector_x or (self.x and self.kind != PAY_ENERGY) or self.counter == ANY_COUNTER or self.among \
            or self.life_rule is not None or (self.kind == EXILE and self.selector is not None) \
            or self.alt is not None or self.named_self or self.source_with_choices


@dataclass(frozen=True)
class AbilityCost:
    numeric_roll_sides: Literal[8] | None = field(default=None, kw_only=True)
    mana: str = ""  # mana symbols, e.g. "{2}{G}"
    mana_allocation: RequirementPlan | None = field(default=None, kw_only=True)
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
    exile_too: bool = False  # -- activated other (wave 42C) -- "Return this card from your graveyard or from exile …" (Mister Immortal): graveyard_only, and the exile zone too (113.6m)
    exile_only110c: bool = False  # -- wave 110C -- exile_too, but not the graveyard: "Put this card from exile onto the battlefield tapped" (Torrent Elemental, 113.6m)
    battlefield_too110k: bool = False  # -- wave 110K -- graveyard_only, and the battlefield too: "Activate only if ~ is on the battlefield or in your graveyard" (Skyblade's Boon)
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
        return self.numeric_roll_sides is not None or any(c.activation_only for c in self.components)

    @property
    def x_chosen(self) -> bool:
        """-- activation costs (wave 4H) -- a part sized by an X announced as it's activated (107.3a, 107.3k):
        "Sacrifice X Treasures", "Remove X ki counters from this creature", "Pay X {E}"."""
        return any((c.x or c.selector_x or c.counters_x) and not c.every for c in self.components)

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
        return self.graveyard_only or any(c.kind == EXILE_FROM_GRAVEYARD and (c.selector is None or c.source_with_choices) for c in self.components)

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
    # Cost-local "mana value X" is announced before targets and payment (107.3a,
    # 602.2b). Keep the ordinary hand-selector grammar conservative elsewhere.
    mv_x = re.search(r" with mana value X(?= from your graveyard$|$)", phrase)
    if mv_x is not None:
        phrase = phrase[:mv_x.start()] + phrase[mv_x.end():]
    quality_union = re.fullmatch(r"(?P<color>white|blue|black|red|green|colorless) or artifact creatures?", phrase)
    if quality_union is not None and zone == "battlefield":
        branches = [selectors.parse(quality_union["color"] + " creature"), selectors.parse("artifact creature")]
        if any(branch is None for branch in branches):
            return None
        keys = []
        for branch in branches:
            assert branch is not None
            compare = (*branch.compare, ("mv", "==", selectors.X_VALUE)) if mv_x is not None else branch.compare
            keys.append(replace(branch, controller="you", other=other, zones=("battlefield",), compare=compare).key())
        return selectors.Selector(zones=("battlefield",), either=tuple(keys)).key()
    if (union := re.fullmatch(r"(other )?artifact creatures and/or Vehicles( you control)?", phrase)) and zone == "battlefield":  # -- (wave 110D) -- Mechtitan Core: either kind counts
        keys = [replace(selectors.parse(p), controller="you", other=other or bool(union[1]), zones=("battlefield",)).key() for p in ("artifact creature", "Vehicle")]  # type: ignore[type-var, union-attr]
        return selectors.Selector(zones=("battlefield",), either=tuple(keys)).key()
    sel = selectors.parse(phrase)
    if mv_x is not None and sel is not None:
        sel = replace(sel, compare=(*sel.compare, ("mv", "==", selectors.X_VALUE)))
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
    from app.rules import wave110d_costs  # -- costs (wave 110D) --

    if (own110d := wave110d_costs.component(part, card_name)) is not None:
        return own110d
    from app.rules import wave110a_activation  # -- costs (wave 110A) --

    if (own110a := wave110a_activation.component(part)) is not None:
        return own110a
    if part == "Exile any number of other cards from your graveyard with four or more card types among them":  # -- (wave 110M) -- Nethergoyf: 601.2h, 205.2a
        return CostComponent(EXILE_FROM_GRAVEYARD, amount=4, more=True, anyn=True, names="types4_110m", text=part,
                             selector=selectors.Selector(card=True, other=True, zone_owner="you", zones=("graveyard",)).key())
    if part == "Exile any number of black cards from your graveyard with fifteen or more black mana symbols among their mana costs":  # -- (wave 110M) -- Baron Helmut Zemo's boast: 601.2h
        return CostComponent(EXILE_FROM_GRAVEYARD, amount=1, more=True, anyn=True, names="black15_110m", text=part,
                             selector=selectors.Selector(card=True, colors=("B",), zone_owner="you", zones=("graveyard",)).key())
    if m := re.fullmatch(r"Sacrifice all (?P<what>.+)", part):
        key = _selector(m["what"], zone="battlefield")
        return CostComponent(SACRIFICE, selector=key, all_objects=True, text=part) if key else None
    if m := re.fullmatch(r"Sacrifice up to (?P<n>\w+) (?P<what>.+)", part):
        base = _component("Sacrifice " + m["n"] + " " + m["what"], card_name)
        return replace(base, up_to=True, text=part) if base and base.kind == SACRIFICE and base.selector else None
    if m := re.fullmatch(r"(.+) with (the same name|different names)", part):
        base = _component(m[1], card_name)
        if base and base.kind in (DISCARD, SACRIFICE) and base.selector and not base.random and base.amount >= 2 and base.names is None:
            return replace(base, names="same" if m[2] == "the same name" else "different", text=part)
        return None
    if m := re.fullmatch(r"Tap any number of (?P<what>untapped creatures you control(?: other than (?:~|this creature))?) with total power (?P<n>\d+) or greater", part):
        sel = selectors.parse(m["what"].replace("other than this creature", "other than ~"))
        return CostComponent("TAP_POWER", amount=int(m["n"]), selector=sel.key(), text=part) if sel is not None else None
    if part == "{T}":
        return CostComponent(TAP, text=part)
    if part == "{Q}":
        return CostComponent(UNTAP, text=part)
    if _MANA_ONLY.match(part):
        return CostComponent(MANA, text=part)
    if re.fullmatch(r"Unattach (?:this \w+|~)", part):
        return CostComponent(UNATTACH, text=part)
    if m := _GRANTER_COST.match(part):  # -- granted from object (wave 18F) -- paid with that object (601.2h): the one choice, made for you
        sel = selectors.parse(m["g"])
        assert sel is not None
        if m["verb"] == "Tap":  # (an untapped one: 118.3)
            return CostComponent(TAP_OTHER, selector=replace(sel, tapped=False).key(), text=part)
        return CostComponent(SACRIFICE if m["verb"] == "Sacrifice" else UNATTACH, selector=sel.key(), text=part)
    if m := _HOST_COST.match(part):  # (the verb's own rules: only an untapped permanent is tapped, 701.26a; only your own is sacrificed, 701.21a: cost_payment)
        sel = selectors.Selector(extras=("host_of_source",), tapped=False if m["verb"] == "Tap" else None)
        return CostComponent(TAP_OTHER if m["verb"] == "Tap" else SACRIFICE, selector=sel.key(), text=part)
    if (m := _SAC_SELF.match(part)) and (not m.group("name") or m.group("name") == card_name):
        return CostComponent(SACRIFICE, text=part)
    if m := _LIFE.match(part):
        return CostComponent(PAY_LIFE, amount=int(m["n"]), text=part)
    if part == 'Pay X life':
        return CostComponent(PAY_LIFE, amount=0, x=True, text=part)
    if m := _ENERGY.match(part):
        if m["n"] == "X":  # -- counters & designations (wave 3E) -- "Pay X {E}" (X chosen as it's activated)
            return CostComponent(PAY_ENERGY, amount=0, x=True, text=part)
        n = m["symbols"].count("{E}") if m["symbols"] else _ENERGY_WORDS.get(m["n"].lower()) or (int(m["n"]) if m["n"].isdigit() else 0)
        return CostComponent(PAY_ENERGY, amount=n, text=part) if n else None
    if part == "Remove a +1/+1 counter or a charge counter from a permanent you control":
        return CostComponent(REMOVE_COUNTER, amount=1, counter=ANY_COUNTER,
                             selector=_selector("permanent you control", zone="battlefield"),
                             counter_options=("+1/+1", "charge"), text=part)
    if m := _REMOVE_ALL.match(part):  # -- activated sweep (wave 26C) -- 602.2b: not announced, it's all of them (casting sets X to that many)
        return CostComponent(REMOVE_COUNTER, amount=0, counter=m["kind"], x=True, every=True, text=part)
    if (m := _REMOVE.match(part)) and (not m.group("name") or m.group("name") == card_name):
        return CostComponent(REMOVE_COUNTER, amount=_n(m["n"]), counter=m["kind"], text=part)
    if _EXILE_SELF_GY.match(part):
        return CostComponent(EXILE_FROM_GRAVEYARD, text=part)
    if (hand_exile := re.fullmatch(r"Exile (?:a|an) (?P<what>(?:[^.,]+? )?card) from your hand", part)) is not None:
        hand_selector = selectors.parse(hand_exile['what'])
        if hand_selector is not None:
            return CostComponent("EXILE_FROM_HAND", selector=hand_selector.key(), text=part)
    if _EXILE_SELF_HAND.match(part):  # -- as long as (wave 37A) -- the source itself, exiled from the hand as the cost is paid (cost_payment: no selector = the source)
        return CostComponent("EXILE_FROM_HAND", text=part)
    if _DISCARD_SELF.match(part):  # -- ability words (wave 4F) -- "Discard this card" (701.9a; 113.6m: from the hand)
        return CostComponent(DISCARD, text=part)
    if _REVEAL_SECRET.match(part):  # -- group choices (wave 53D) --
        return CostComponent(REVEAL_SECRET, text=part)
    if _REVEAL_SELF.match(part):  # -- forecast (wave 24C) -- revealed to everyone (701.20a), the card stays in the hand
        return CostComponent(REVEAL_SELF, text=part)
    if part == 'Reveal your hand':
        return CostComponent(REVEAL_HAND, text=part)
    if part == "Exile a spell you control":
        return CostComponent(EXILE, selector=selectors.Selector(zones=("stack",), controller="you").key(), text=part)
    if _EXILE_SELF.match(part):
        return CostComponent(EXILE, text=part)
    if _RETURN_SELF.match(part):
        return CostComponent(RETURN_PERMANENT, text=part)
    if _BOTTOM_SELF.match(part):
        return CostComponent(LIBRARY_BOTTOM_SELF, text=part)
    if m := _SAC_CHOSEN.match(part):
        key = _selector(m["what"], zone="battlefield", other=m["n"] == "another")
        if key is None and m["n"] in ("a", "an", "another") and " or " in m["what"]:  # -- keywords (wave 43C) -- "Sacrifice a legendary artifact or legendary creature"
            one, two = m["what"].split(" or ", 1)  # (wave 50G: "Sacrifice another creature or a Blood token" (Anje): "another" is the first kind's only, the second kind has its own article)
            if m["what"].endswith(" or token") and m["what"].count(" or ") == 2:  # -- if you do (wave 100B) -- "an artifact, enchantment, or token" (Devouring Sugarmaw)
                one, two = m["what"].rsplit(" or ", 1)
            first, second = _selector(one, zone="battlefield", other=m["n"] == "another"), \
                _selector(re.sub(r"^an? ", "", two), zone="battlefield", other=m["n"] == "another" and not re.match(r"an? ", two))  # (Sauron, the Dark Lord's ward): two kinds, each;
            # ("another creature or token" (Ice Cream Kitty): no article of its own, so "another" covers both, as in "another artifact or creature")
            return CostComponent(SACRIFICE, selector=first, alt=second, text=part) if first and second else None  # with its own adjective: either one
        return CostComponent(SACRIFICE, amount=_n(m["n"]), selector=key, text=part) if key else None
    if part == 'Discard a legendary card with the same name as a legendary permanent you control':
        permanent = selectors.Selector(controller='you', supertypes=('Legendary',)).key()
        card = selectors.Selector(card=True, zones=('hand',), zone_owner='you', supertypes=('Legendary',),
                                  extras=('samename_among:' + permanent,))
        return CostComponent(DISCARD, amount=1, selector=card.key(), text=part)
    if part == "Discard the last card you drew this turn":
        hand = selectors.Selector(card=True, zones=("hand",), zone_owner="you",
                                  extras=("last_drawn_this_turn107",)).key()
        return CostComponent(DISCARD, amount=1, selector=hand, text=part)
    if m := _DISCARD.match(part):
        if m["n"] == "another":
            return None
        key = _selector(m["what"], zone="hand")
        if key is None and m["n"] in ("a", "an", "one") and not m["random"] and " or " in m["what"]:
            first, second = re.split(r" or (?=an? )", m["what"], maxsplit=1) if re.search(r" or an? ", m["what"]) else m["what"].split(" or ", 1)  # (wave 110F: "an instant or sorcery card or a creature card with flying")
            left = _selector(first, zone="hand")
            right = _selector(re.sub(r"^an? ", "", second), zone="hand")
            # 701.9a / 602.2b: discard one card matching either complete description.
            return CostComponent(DISCARD, selector=left, alt=right, text=part) if left and right else None
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
        if m['what'] == 'permanent you control or suspended card you own' and not other:
            sel = selectors.parse(m['what'])
            key = sel.key() if sel is not None else None
        else:
            key = _selector(m["what"], zone="battlefield", other=other)
        return CostComponent(REMOVE_COUNTER, amount=_n(m["n"]), counter=m["kind"], selector=key, text=part) if key else None
    return None


def parse_ability_cost(cost: str, *, card_name: str = "", loyalty: bool = False, anyn: bool = True) -> AbilityCost:
    from app.rules import source_named_cost69

    if not loyalty and (source69 := source_named_cost69.parse(cost)) is not None:
        return source69
    if not loyalty and cost.strip() == '{6}, Roll a d8':
        return replace(parse_ability_cost('{6}', card_name=card_name, anyn=anyn), numeric_roll_sides=8)
    cost = re.sub(r'Remove twelve ([\w+/\-]+) counters from ([^,{}:]+?) and exile it', r'Remove 12 \1 counters from \2, Exile \2', cost)
    from app.rules import wave110d_costs  # -- costs (wave 110D) --

    cost = wave110d_costs.rewrite(cost)
    cost = cost.replace(", Choose flying, first strike, trample, or shadow", "")  # -- wave 110J -- Phyrexian Splicer: the choice is the ability's mode (wave110j_cards._splicer)
    if loyalty:
        raw = cost.strip().replace("−", "-")
        if raw.upper() == "-X":
            return AbilityCost(loyalty_x=True, components=(CostComponent(LOYALTY, text=cost),))
        if raw.upper().lstrip("+-") == "X":
            return AbilityCost(unsupported=(cost,))
        return AbilityCost(loyalty=int(raw), components=(CostComponent(LOYALTY, amount=int(raw), text=cost),))
    from app.rules import activation_alternatives

    if (sides := activation_alternatives.sides(cost)) is not None:
        return AbilityCost(either=tuple(parse_ability_cost(side, card_name=card_name, anyn=anyn) for side in sides))
    from app.rules import defined_activation_x

    if defined_activation_x.counter_cost(cost) is not None:
        return AbilityCost(mana="{X}", components=(CostComponent(MANA, text="{X}"),))
    # A fixed named-card cost may contain commas in the name. Preserve it as
    # one component before ordinary payment separators or source substitution;
    # a renamed copy still discards the explicitly named card (201.5, 707.10).
    whole = cost.strip()
    if _GRANDEUR.fullmatch(whole) and not re.search(r"[{}:]|, (?:Pay|Discard|Sacrifice|Tap|Untap|Remove|Exile|Return|Reveal)\b", whole):
        fixed = _component(whole, card_name) or _one_4h(whole, card_name)
        if fixed is not None:
            return AbilityCost(components=(fixed,))
    components: list[CostComponent] = []
    unsupported: list[str] = []
    cost = cost.replace("half your life, rounded up", "half your life rounded up")  # (one part: wave 4H)
    # -- tutor (wave 26D) -- "Sacrifice a red creature, a green creature, and a white creature" (the Heralds): one part, three objects
    cost = re.sub(r"(Sacrifice (?:an?|another) [^,{}:]+?), ((?:an?|another) [^,{}:]+?), and ((?:an?|another) [^,{}:]+?)(?=,|$)",
                  r"\1 and \2 and \3", cost)
    cost = re.sub(r"(Sacrifice (?:this \w+|~)) and (any number of (?:other )?[^,{}:]+)", r"\1, Sacrifice \2", cost)  # -- any number as an additional cost (wave 48B) -- Emrakul's Evangel: two parts
    if card_name and "," in card_name:  # (wave 4H) "Discard another card named Korlash, Heir to Blackblade": one part
        cost = cost.replace(card_name, "~")
    # -- static_other (wave 36B) -- "Tap three untapped Advisors, Artificers, and/or Monks you control" (The Archimandrite): one part naming three kinds
    cost = re.sub(r"(Tap \w+ (?:other )?untapped )([A-Z][\w'-]*), ([A-Z][\w'-]*),? and/or ([A-Z][\w'-]*)(?= you control)", r"\1\2 or \3 or \4", cost)
    # -- commanders (wave 47A) -- "Remove three counters from among other artifacts, creatures, and planeswalkers you control" (Tekuthal): one part naming three kinds
    cost = re.sub(r"(Remove \w+ (?:[+\-/\w]+ )?counters? from among (?:other )?)(\w+), (\w+), (?:and|or) (\w+)(?= you control)", r"\1\2 or \3 or \4", cost)
    # 122.1 / 602.2b: commas within a list of eligible permanent types aren't
    # separators between payments (Soul Diviner). Keep this limited to an OR list.
    types = r"(?:artifact|creature|land|planeswalker|enchantment|battle)"
    cost = re.sub(rf"(Sacrifice an? )((?:{types}, )+or {types})(?=,|$)",
                  lambda m: m[1] + m[2].replace(", or ", " or ").replace(", ", " or "), cost)
    cost = re.sub(rf"(Remove (?:a|one) counter from an? )((?:{types}, )+or {types})(?= you control)",
                  lambda m: m[1] + m[2].replace(", or ", " or ").replace(", ", " or "), cost)
    for part in (p.strip() for p in cost.split(",")):
        if not part:
            continue
        found = _component(_self_text(part, card_name), card_name) or (any_number_part(part, 0) if anyn else None)  # (-- any number as an additional cost (wave 48B) -- "Exile any number of cards from your graveyard": an activation cost; not an optional payment's (its own "any number" instruction) nor a mana ability's)
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
    if any(c.x and re.search(r"any number of|one or more", c.text) for c in components) and sum(
            c.x or (c.kind == MANA and "X" in c.text) for c in components) > 1:
        unsupported.append(cost)  # Independent variable costs cannot share the one announced X (601.2b).
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
_X_SELF = re.compile(rf"^Remove (?P<n>X|any number of|one or more) (?P<kind>[\w+/\-]+) counters from {_SELF}$")
_COUNTER_NUMBERS = "|".join(w for w in _WORDS if w != "another") + r"|\d+"
_AMONG = re.compile(rf"^Remove (?P<n>{_COUNTER_NUMBERS}|X|any number of|one or more) (?:(?P<kind>\+1/\+1|-1/-1|[a-z]+) )?counters? from among (?P<what>.+ you control)$")
_PUT_SELF = re.compile(rf"^Put {_N} (?P<kind>[\w+/\-]+) counters? on {_SELF}$")
_PUT_CHOSEN = re.compile(rf"^Put {_N} (?P<kind>[+-]\d+/[+-]\d+) counters? on (?P<another>a|an|another) (?P<what>[^,]+ (?:you control|an opponent controls))$")
_BLIGHT = re.compile(r"^Blight (?P<n>\d+|X)$")
_SAC_X = re.compile(r"^Sacrifice X (?P<what>.+)$")
_TAP_X = re.compile(r"^Tap X untapped (?P<what>.+ you control)$")
_EXILE_GY_X = re.compile(r"^Exile X (?P<what>(?:[\w\-]+ )*cards from your graveyard)$")
_MILL = re.compile(rf"^Mill (?:a card|{_N} cards)$")
_EXILE_TOP = re.compile(rf"^Exile the top (?:card|{_N} cards) of your library$")
_EXILE_CHOSEN = re.compile(rf"^Exile {_N} (?P<what>[^,]+ you control)$")
_EXILE_TO_GY = re.compile(r"^Put (?:(?P<one>a) card an opponent owns from exile into that player's graveyard"
                          r"|(?P<n>two|three) cards your opponents own from exile into their owners' graveyards)$")  # (wave 15C)
_EVIDENCE = re.compile(r"^Collect evidence (?P<n>\d+)$")
# -- exile for total mana value (wave 110C) -- "Exile any number of historic cards from your graveyard with total mana value 30 or greater" (The Capitoline Triad):
# the collect-evidence payment (701.59a) on a kind of card, and not collecting evidence (cost_payment skips the designation)
_EXILE_TOTAL = re.compile(r"^Exile any number of (?P<what>[a-z]+) cards from your graveyard with total mana value (?P<n>\d+) or greater$")
# "Exile an artifact from among permanents you control and/or cards in your graveyard" / "…two creatures…" / "…one or more Dinosaurs…"
_CRAFT = re.compile(r"^Exile (?P<n>a|an|one|two|three|four|five|six|seven|\d+)(?P<more> or more)?(?: (?P<what>[^,]+?))? from among "
                    r"permanents you control and/or cards in your graveyard$")
_WATERBEND = re.compile(r"^(?:Waterbend|Tapbend) \{(?P<n>\d+|X)\}$")
_SAC_OR = re.compile(r"^Sacrifice (?P<a>a|an|another) (?P<w1>[\w\-]+) or (?P<b>a|an|another) (?P<w2>[\w\-]+)$")  # (no article: refused)
_GRANDEUR = re.compile(r"^Discard another card named (?P<name>~|[A-Z].+)$")  # (grandeur, an ability word: 207.2c)
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

    if part in ("Put a card exiled with ~ into its owner's graveyard", "Put a creature card exiled with ~ into its owner's graveyard"):  # (wave 110D: Shelob, Dread Weaver)
        key = selectors.Selector(card=True, zones=('exile',), extras=('source_linked',), types=("Creature",) if " creature " in part else ()).key()
        return CostComponent(EXILE_TO_GY, amount=1, selector=key, text=part)
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
    if m["what"] == "nonlands with activated abilities" and n is not None:  # -- (wave 110D) -- The Enigma Jewel: a nonland permanent you control or nonland card in your graveyard
        return CostComponent(CRAFT, amount=n, selector=_selector("nonland permanent with activated abilities you control", zone="battlefield"),
                             alt=_selector("nonland card with activated abilities from your graveyard", zone="graveyard"), more=bool(m["more"]), text=part)
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
    from app.rules import colored_reveal_x87

    if (colored87 := colored_reveal_x87.component(part)) is not None:
        return colored87
    from app.rules import fixed_top_graveyard_cost46, ordered_zone_costs46

    if (fixed_top := fixed_top_graveyard_cost46.component(part)) is not None:
        return fixed_top
    if (ordered := ordered_zone_costs46.component(part)) is not None:
        return ordered
    from app.rules import counter_x_costs43

    if (counter_x := counter_x_costs43.parse(part)) is not None:
        return counter_x
    if part == 'Exile a face-down permanent you control face up':
        # Native exile costs move to ordinary face-up exile; no turn-face-up action.
        found = _one_4h('Exile a face-down permanent you control', card_name)
        return replace(found, text=part) if found is not None else None
    if m := _ANY_SELF.match(part):
        return CostComponent(REMOVE_COUNTER, amount=_n(m["n"]), counter=ANY_COUNTER, text=part)
    if m := _ANY_CHOSEN.match(part):
        key = _selector(m["what"], zone="battlefield", other=m["another"] == "another")
        return CostComponent(REMOVE_COUNTER, counter=ANY_COUNTER, selector=key, text=part) if key else None
    if m := _X_SELF.match(part):
        return CostComponent(REMOVE_COUNTER, amount=int(m["n"] == "one or more"), counter=m["kind"], x=True,
                             more=m["n"] == "one or more", text=part)
    if m := _AMONG.match(part):  # -- activated sweep (wave 26C) -- 122.1: the counters come off any of the permanents, one pick for each counter
        key = _selector(m["what"], zone="battlefield")  # (wave 47A: "other" is the selector's own, Tekuthal: the permanent paying isn't among them)
        if key is None:
            return None
        variable = m["n"] in ("X", "any number of", "one or more")
        return CostComponent(REMOVE_COUNTER, amount=int(m["n"] == "one or more") if variable else _n(m["n"]),
                             counter=m["kind"] or ANY_COUNTER, selector=key, x=variable, more=m["n"] == "one or more", among=True, text=part)
    if m := _PUT_SELF.match(part):
        return CostComponent(PUT_COUNTER, amount=_n(m["n"]), counter=m["kind"], text=part) if m["n"] != "another" else None
    if m := _PUT_CHOSEN.match(part):
        if m["what"].endswith("an opponent controls"):
            # CR 118.3, 702.24a: putting counters may pay on an opponent's
            # permanent (Sheltering Ancient); sacrificing still requires yours.
            sel = selectors.parse(m["what"])
            key = sel.key() if sel is not None else None
        else:
            key = _selector(m["what"], zone="battlefield", other=m["another"] == "another")
        return CostComponent(PUT_COUNTER, amount=_n(m["n"]), counter=m["kind"], selector=key, text=part) \
            if key and m["n"] != "another" else None
    if m := _BLIGHT.match(part):  # 701.68a: put N -1/-1 counters on a creature you control
        key = _selector("creature you control", zone="battlefield")
        if m["n"] == "X":  # (wave 110C: Soul Immolation; the cap on X is casting.life_x_problem)
            return CostComponent(PUT_COUNTER, amount=0, counter="-1/-1", selector=key, text=part, counters_x=True) if key else None
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
    if part == "Exile cards from your graveyard equal to the number of opponents you have":
        key = _selector("cards from your graveyard", zone="graveyard")
        return CostComponent(EXILE_FROM_GRAVEYARD, amount=0, selector=key, text=part, amount_rule="opponents") if key else None
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
    if m := _EXILE_TOTAL.match(part):  # (wave 110C)
        key = _selector(f"{m['what']} cards from your graveyard", zone="graveyard")
        return CostComponent(COLLECT_EVIDENCE, amount=int(m["n"]), selector=key, text=part) if key and int(m["n"]) > 0 else None
    if part == "Forage":  # 701.61a
        return CostComponent(FORAGE, amount=3, text=part)
    if m := _SAC_OR.match(part):  # "another" belongs to its own alternative only (Mold Folk; Malevolent Noble)
        first = _selector(m["w1"], zone="battlefield", other=m["a"] == "another")
        second = _selector(m["w2"], zone="battlefield", other=m["b"] == "another")
        return CostComponent(SACRIFICE, selector=first, alt=second, text=part) if first and second else None
    if part == "Exert ~":  # 701.43a: it won't untap during your next untap step (engine.start_next_turn)
        return CostComponent(EXERT, text=part)
    if (grandeur := _GRANDEUR.match(part)) is not None:
        fixed = grandeur["name"] != "~"
        key = _selector("card named " + grandeur["name"] if fixed else "card", zone="hand", other=True)
        return CostComponent(DISCARD, selector=key, named_self=not fixed, text=part) if key else None
    if part == _HALF_LIFE:
        return CostComponent(PAY_LIFE, amount=0, life_rule="half", text=part)
    if part == _COMMANDER_LIFE:
        return CostComponent(PAY_LIFE, amount=0, life_rule="commander_colors", text=part)
    if (each := re.fullmatch(r"Pay (?P<n>\d+) life for each (?P<k>[a-z]+) counter on (?:~|this enchantment)", part)) is not None:  # -- activated (wave 100I) -- (Tornado:
        return CostComponent(PAY_LIFE, amount=0, life_rule=f"per_counter100i:{each['k']}:{each['n']}", text=part)  # counted as it's paid, 601.2f-h)
    return None


def wave4h_parts(part: str, card_name: str) -> list[CostComponent] | None:
    """The part as one or more components (two joined by "and": the second keeps the first's verb when it has none,
    "it" being the source), or None when any piece isn't read."""
    if m := _WATERBEND.match(part):
        from app.rules import waterbend102

        piece=waterbend102.part(part)
        return [CostComponent(MANA,text=f"{{{m['n']}}}"),piece] if piece is not None else None
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
_KICKER = re.compile(r"^(?:(?P<multi>multi)?kicker|(?P<many>squad|replicate)|(?P<once>offspring)|(?P<entwine>entwine)) (?P<cost>(?:\{[^}]+\})+)(?P<anytimes> any number of times)?$",
                     re.IGNORECASE)
# -- keywords (wave 50H) -- 702.33b: "Kicker {A} and/or {B}" is "Kicker {A}, kicker {B}": two kicker costs, each paid at most once (Invasion's Battlemages)
_KICKER2 = re.compile(r"^kicker (?P<a>(?:\{[^}]+\})+) and/or (?P<b>(?:\{[^}]+\})+)(?P<any> any number of times)?$", re.IGNORECASE)


# -- casting extras (wave 18E) -- 702.42a: an entwine cost that isn't mana ("Entwine—Sacrifice three lands.") is paid as additional costs are
_ENTWINE_EXTRA = re.compile(r"^entwine—(?P<rest>[^{}.]+)$", re.IGNORECASE)


def _entwine_extra(line: str) -> str | None:
    """The non-mana entwine cost of a line the engine pays ("sacrifice two lands"), or None."""
    from app.rules import alt_costs

    m = _ENTWINE_EXTRA.fullmatch(re.sub(r"\s*\(.*?\)", "", line).strip().rstrip("."))
    return m["rest"].strip() if m is not None and alt_costs.parse_cost(m["rest"].strip()) is not None else None


# -- cast keywords (wave 43D) -- 702.33a, 702.157a, 702.56a: a kicker / squad / replicate cost that isn't mana ("Kicker—Sacrifice a land.",
# "Squad—Exile four cards from your graveyard.", "Replicate—Pay {E}{E}{E}.") is an optional additional cost made of the parts an alternative cost
# may have (alt_costs.parse_cost); paid with the other additional costs, once for each time it is paid (601.2b, 601.2h)
# ponytail: squad / replicate have no menu entry in the frontend (only the cast_spell ``kicker`` count), mana or not
_KICKER_EXTRA = re.compile(r"^(?:(?P<multi>multi)?kicker|(?P<many>squad|replicate))—(?P<rest>[^{}]+|pay (?:\{E\})+)$", re.IGNORECASE)


def kicker_extra_parts(line: str) -> tuple[bool, str] | None:
    """(paid any number of times, the cost) of a "Kicker—…" / "Squad—…" / "Replicate—…" line whose cost isn't mana, or None."""
    from app.rules import alt_costs

    m = _KICKER_EXTRA.fullmatch(re.sub(r"\s*\(.*?\)", "", line).strip().rstrip("."))
    if m is None:
        return None
    rest = m["rest"].strip()
    if (e := re.fullmatch(r"(?i)pay ((?:\{E\})+)", rest)) is not None:  # ("Pay {E}{E}{E}" is "pay three {E}")
        words = {v: k for k, v in _ENERGY_WORDS.items() if k not in ("a", "an", "one")}
        n = e[1].count("{E}")
        rest = f"pay {words[n]} {{E}}" if n in words else rest
    rest = rest[:1].lower() + rest[1:]
    found = alt_costs.parse_cost(rest)
    return (bool(m["multi"] or m["many"]), rest) if found is not None and not found.mana else None


# -- keywords (wave 50H) -- 702.33a: "Kicker—{2}{R}, Sacrifice a land." (Dwarven Landslide): a mana part and parts an alternative cost may have, the mana added to the total
# cost and the rest paid with the other additional costs, once
_KICKER_MIXED = re.compile(r"^(?P<k>kicker|squad)—(?P<mana>(?:\{[^}X]+\})+), (?P<rest>[^{}]+)$", re.IGNORECASE)


def kicker_mixed_parts(line: str) -> tuple[str, str, bool] | None:
    """(the mana, the other parts, paid any number of times) of a "Kicker—{mana}, [parts]" / "Squad—{mana}, [parts]" (wave 110E) line the engine pays, or None."""
    from app.rules import alt_costs

    m = _KICKER_MIXED.fullmatch(re.sub(r"\s*\(.*?\)", "", line).strip().rstrip("."))
    if m is None or not _MANA_ONLY.match(m["mana"]):
        return None
    rest = m["rest"].strip()
    rest = rest[:1].lower() + rest[1:]
    found = alt_costs.parse_cost(f"pay {m['mana']} and {rest}")
    return (m["mana"], rest, m["k"].lower() == "squad") if found is not None and found.mana == m["mana"] and found.cost.components else None


def positive_kicker_x(line: str) -> str | None:
    """An actual keyword's explicit lower bound on its single announced kicker X."""
    suffix = ". X can't be 0"
    text = line.strip().rstrip(".")
    if not text.endswith(suffix):
        return None
    match = _KICKER.fullmatch(text[:-len(suffix)])
    return match["cost"] if match is not None and match["cost"].upper().count("{X}") == 1 and not any(
        match[k] for k in ("multi", "many", "once", "entwine", "anytimes")) and _MANA_ONLY.match(match["cost"]) else None


def kicker_line(line: str) -> bool:
    """Is this keyword line a kicker the engine pays ("Kicker {2}{R}", "Multikicker {1}")?"""
    if positive_kicker_x(line) is not None:
        return True
    if _entwine_extra(line) is not None or kicker_extra_parts(line) is not None or kicker_mixed_parts(line) is not None:
        return True
    if (two := _KICKER2.fullmatch(line.strip().rstrip("."))) is not None:  # (-- keywords (wave 50H) -- both mana only, no {X})
        return all(_MANA_ONLY.match(c) and "{X}" not in c.upper() for c in (two["a"], two["b"]))
    m = _KICKER.fullmatch(line.strip().rstrip("."))
    # (-- cast keywords (wave 43D) -- 107.3a: "Kicker {X}" / "Kicker {X}{2}", one {X} and paid once: X is announced with the kicker cost)
    one_x = m is not None and m["cost"].upper().count("{X}") == 1 and not (m["multi"] or m["many"] or m["once"] or m["entwine"])
    return m is not None and ("{X}" not in m["cost"].upper() or one_x) and _MANA_ONLY.match(m["cost"]) is not None


@dataclass(frozen=True)
class Kicker:
    cost: str  # mana symbols, e.g. "{2}{R}"
    multi: bool = False  # 702.33c multikicker: any number of times
    entwine: bool = False  # -- casting extras (wave 18E) -- 702.42a: the count 1 means "choose all modes" (paid as kicker is)
    extra: str = ""  # (an entwine cost that isn't mana: "sacrifice two lands", paid with the additional costs)
    text: str = ""  # -- free-cast optional costs (wave 41D) -- the keyword line ("Kicker {R}", "Squad {2}"): the label of the question
    second: str = ""  # -- keywords (wave 50H) -- 702.33b: "Kicker {A} and/or {B}": B, the second kicker cost. Then the cast's ``kicker`` is a mask (1: A, 2: B, 3: both)
    anytimes: bool = False  # -- (wave 110F) -- Taste of Paradise: "you may pay {1}{G} any number of times" repeats like multikicker but isn't kicker (702.33c): the spell is not "kicked"
    minimum_x: int = 0  # Only the actual selected keyword may constrain its announced X.

    def paid(self, times: int) -> int:
        """-- keywords (wave 50H) -- how many kicker costs the cast's ``kicker`` pays (702.33d): the bits of the mask of two costs, else the count."""
        if self.second and self.multi:  # -- wave 110G -- Primitive Justice: ``times`` is first count + 32 * second count (each 0..30)
            return pair_counts(times)[0] + pair_counts(times)[1]
        return bin(times).count("1") if self.second else times

    @property
    def x(self) -> bool:
        """-- cast keywords (wave 43D) -- 107.3a: "Kicker {X}": the value of X is announced with the kicker cost."""
        return "{X}" in self.cost.upper()


def pair_counts(times: int) -> tuple[int, int]:
    """-- wave 110G -- the two payment counts of "you may pay {A} and/or {B} any number of times" in the cast's ``kicker`` number."""
    return times & 31, times >> 5


_OPTIONAL_EXTRA = re.compile(r"As an additional cost to cast this spell, you may pay (?P<cost>\{2\}\{R\})\.")  # -- (wave 110O) -- Undergrowth, the one printed wording


def kicker_cost(abilities: Iterable[AbilityText]) -> Kicker | None:
    """702.33a / 702.33c: the card's "Kicker {cost}" or "Multikicker {cost}" line (mana only), or
    None. Two kicker costs ("Kicker {1}{U} and/or {2}{B}", 702.33b), non-mana kicker costs
    ("Kicker—Sacrifice a land") and X in the cost stay manual."""
    found: list[Kicker] = []
    for ab in abilities:
        if (opt := _OPTIONAL_EXTRA.fullmatch(ab.text.strip())) is not None and ab.kind == "spell":  # -- (wave 110O) -- 601.2b, 118.8: "you may pay {2}{R}" is an optional additional cost, read as a kicker
            found.append(Kicker(opt["cost"], text=ab.text.strip().rstrip(".")))
            continue
        if ab.kind != "keywords" or not ({"kicker", "multikicker", "squad", "replicate", "offspring", "entwine"} & set(ab.keywords)):
            continue
        if (positive := positive_kicker_x(ab.text)) is not None:
            found.append(Kicker(positive, text=ab.text.strip().rstrip("."), minimum_x=1))
            continue
        if (extra := _entwine_extra(ab.text)) is not None:
            found.append(Kicker("", entwine=True, extra=extra))
            continue
        if (mixed := kicker_mixed_parts(ab.text)) is not None:  # (wave 50H)
            found.append(Kicker(mixed[0], multi=mixed[2], extra=mixed[1], text=ab.text.strip().rstrip(".")))
            continue
        if (non_mana := kicker_extra_parts(ab.text)) is not None:  # (wave 43D)
            found.append(Kicker("", multi=non_mana[0], extra=non_mana[1], text=ab.text.strip().rstrip(".")))
            continue
        if (two := _KICKER2.fullmatch(ab.text.strip().rstrip("."))) is not None and kicker_line(ab.text):  # (wave 50H)
            found.append(Kicker(two["a"], second=two["b"], multi=bool(two["any"]), anytimes=bool(two["any"]), text=ab.text.strip().rstrip(".")))  # (wave 110G: "any number of times", Primitive Justice)
            continue
        m = _KICKER.fullmatch(ab.text.strip().rstrip("."))
        if m is None or not kicker_line(ab.text):
            return None
        found.append(Kicker(m["cost"], multi=bool(m["multi"] or m["many"]), entwine=bool(m["entwine"]), anytimes=bool(m["anytimes"]), text=ab.text.strip().rstrip(".")))
    return found[0] if len(found) == 1 else None


# -- costs (wave 3$) -- additional costs to cast a spell (118.8, 601.2b) ----------------------------------
_THROWDOWN_COST = "As an additional cost to cast this spell, sacrifice a creature or sacrifice a modified creature."
_ADDITIONAL = re.compile(r"^as an additional cost to cast (?:this spell|~), (?P<cost>[^.]+)\.?$", re.IGNORECASE)
# What a spell's additional cost may be made of: parts with chosen objects (or life / energy). Never the
# source itself (a spell isn't on the battlefield to be sacrificed), tapping it, mana or counters on it.
# -- static_other sweep (wave 17C) -- also "reveal a Merfolk card from your hand" (REVEAL_FROM_HAND, as optional_payment reads it),
# "behold an Elf" (701.4a: reveal an Elf card from your hand or choose an Elf you control), "blight 1" (701.68a), "forage" (701.61a)
# and "exile a creature you control": the parts of an activation cost cost_payment already pays
BEHOLD = "BEHOLD"
BEHOLD_EXILE = "BEHOLD_EXILE"  # One matching controlled permanent or hand card, exiled as a single additional cost.
_ADDITIONAL_KINDS = frozenset({SACRIFICE, DISCARD, PAY_LIFE, PAY_ENERGY, EXILE_FROM_GRAVEYARD, RETURN_PERMANENT, TAP_OTHER,
                               EXILE_TO_GY,  # (EXILE_TO_GY: wave 15C)
                               "REVEAL_FROM_HAND", BEHOLD, BEHOLD_EXILE, PUT_COUNTER, FORAGE, EXILE,
                               "DISCARD_HAND"})  # (-- wave 110M -- 701.9a: "discard your hand", Kaervek's Spite; the spell is on the stack by then, so not in it)
_REVEAL_HAND_COST = re.compile(r"^Reveal (?:a|an) (?P<what>.+? card) from your hand$")
_BEHOLD_COST = re.compile(r"^Behold (?:(?P<one>a|an)|(?P<n>two|three|four|five)) (?P<q>[A-Z][a-z]+)$")  # (-- cast keywords (wave 43D) -- "Behold three Elementals")


def _extra_part(part: str) -> CostComponent | None:
    """-- static_other sweep (wave 17C) -- one of the parts above that a spell's additional cost may also be made of."""
    if part == "Choose a creature you control or reveal a creature card from your hand":  # 701.4a (wave 110A): Monstrous Emergence
        return _extra_part("Behold a Creature")
    if m := _REVEAL_HAND_COST.match(part):
        key = _selector(m["what"], zone="hand")
        return CostComponent("REVEAL_FROM_HAND", selector=key, text=part) if key else None
    if m := _BEHOLD_COST.match(part):
        from app.rules.selectors import _IRREGULAR

        # (701.4a, wave 43D: "Behold three Elementals" — three objects, each a card revealed from your hand or a permanent you control, none twice)
        quality = _IRREGULAR.get(m["q"].lower()) or (m["q"][:-1] if m["n"] and m["q"].endswith("s") else m["q"])
        hand, field = _selector(f"{quality} card", zone="hand"), _selector(f"{quality} you control", zone="battlefield")
        return CostComponent(BEHOLD, amount=_WORDS[m["n"]] if m["n"] else 1, selector=hand, alt=field, text=part) if hand and field else None
    found = _one_4h(part, "")
    if found is not None and (found.kind == FORAGE or (found.kind == PUT_COUNTER and part.startswith("Blight"))
                              or (found.kind == EXILE and found.selector is not None and not found.x)):
        return found
    return None


# -- cost reductions paid with objects (wave 47C) -- 601.2b, 601.2f: "you may sacrifice any number of creatures" / "exile any number of blue cards from your hand" / "tap any
# number of untapped creatures you control": the part is paid with the rest (601.2h) and each object chosen takes ``per`` generic mana off the total cost
_ANY_NUMBER = re.compile(r"^(?P<verb>sacrifice|exile|tap) (?:any number of|(?P<one>one or more)) (?P<what>.+?)(?: from your (?P<zone>hand|graveyard))?$", re.IGNORECASE)  # (wave 48B: "one or more": at least one)


_ANY_COUNTERS = re.compile(r"^remove any number of (?P<kind>[+\-]\d+/[+\-]\d+) counters from among (?P<what>creatures you control)$", re.IGNORECASE)


def any_number_part(text: str, per: int) -> CostComponent | None:
    if (c := _ANY_COUNTERS.match(text.strip())) is not None and per > 0:  # (122.1: the counters come off any of the creatures, one pick for each, as for "from among")
        key = _selector(c["what"], zone="battlefield")
        return CostComponent(REMOVE_COUNTER, amount=0, counter=c["kind"], selector=key, among=True, up_to=True, reduces=per, anyn=True, text=text[:1].upper() + text[1:]) if key else None
    m = _ANY_NUMBER.match(text.strip())
    if m is None or per < 0:
        return None
    verb, zone = m["verb"].lower(), (m["zone"] or "battlefield").lower()
    if (verb == "exile") == (zone == "battlefield"):
        return None  # (sacrifice and tap are of permanents; exile is of the hand or the graveyard)
    key = _selector(m["what"].replace(" and/or ", " or ") + (" from your graveyard" if zone == "graveyard" else ""), zone=zone)
    kind = {"sacrifice": SACRIFICE, "tap": TAP_OTHER}.get(verb) or (EXILE_FROM_GRAVEYARD if zone == "graveyard" else "EXILE_FROM_HAND")
    one = m["one"] is not None  # (-- any number as an additional cost (wave 48B) -- "Sacrifice one or more artifacts" (Radiant Lotus): at least one, so the cost can be cancelled but not paid with none)
    return CostComponent(kind, amount=int(one), selector=key, up_to=not one, more=one, reduces=per, anyn=True, text=text[:1].upper() + text[1:]) if key else None


def additional_cost_text(line: str) -> str | None:
    """"As an additional cost to cast this spell, sacrifice a creature." → "sacrifice a creature"."""
    if line.strip() == _THROWDOWN_COST:  # -- wave 110E -- 118.8: a modified creature is a creature, so "or a modified creature" adds no choice (Lethal Throwdown)
        return "sacrifice a creature"
    m = _ADDITIONAL.match(line.strip())
    if m is None and line.strip().lower().rstrip(".") == ("as an additional cost to cast this spell, blight x. x can't be greater than the greatest "
                                                         "toughness among creatures you control"):
        return "blight X"  # -- blight X (wave 110C) -- the cap is checked as X is announced (casting.life_x_problem)
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
    from app.rules import waterbend102

    if (water := waterbend102.part(text)) is not None:
        return AbilityCost(components=(water,))
    from app.rules import wave110a_activation  # -- costs (wave 110A) --

    if (half110a := wave110a_activation.component(text)) is not None:
        return AbilityCost(components=(half110a,))
    if text.lower() == "collect evidence x, where x is the total mana value of the permanents this spell targets":  # Urgent Necropsy: 701.59a, 601.2b
        key = _selector("cards from your graveyard", zone="graveyard")
        return AbilityCost(components=(CostComponent(COLLECT_EVIDENCE, amount=0, selector=key, text="Collect evidence X", targets_mv110g=True),)) if key else None
    if text == 'put a -1/-1 counter on a creature you control':
        counter = _one_4h(text[:1].upper() + text[1:], '')
        return AbilityCost(components=(counter,)) if counter is not None and counter.selector is not None else None
    if (behold_exile := re.fullmatch(r"behold (an? [A-Z][a-z]+) and exile it", text)) is not None:
        behold_exile_part = _extra_part('Behold ' + behold_exile[1])
        if behold_exile_part is not None:
            return AbilityCost(components=(replace(behold_exile_part, kind=BEHOLD_EXILE, text=text[:1].upper() + text[1:]),))
        return None
    either = _either(text)  # -- static wordings (wave 6E) --
    if either is not None:
        return either if either.either else None
    if text == "pay X life":  # -- X sized by a count (wave 4K) -- Toxic Deluge: X announced as it's cast (601.2b,
        return AbilityCost(life_x=True)  # 107.3a), paid with the rest (601.2h), at most your life (119.4, 118.3)
    text = re.sub(r"\b(\w+), (\w+), and/or (\w+)\b", r"\1 or \2 or \3", text)  # (wave 17C: "tap two untapped artifacts, creatures, and/or lands")
    # -- any number as an additional cost (wave 48B) -- 601.2b: "sacrifice any number of creatures" / "you may sacrifice any number of Spirits" (Devouring Greed) /
    # "tap any number of untapped creatures you control" (Burn at the Stake): zero is allowed, so the "you may" changes nothing; what the effect reads is how many were paid
    text = re.sub(r"^(you may (?:sacrifice|tap)) one or more ", r"\1 any number of ", text, flags=re.IGNORECASE)  # (optional, so "one or more" is none or more: Plumb the Forbidden)
    if (any_n := re.fullmatch(r"(?:you may )?((?:sacrifice|tap) any number of [^,]+)", text, re.IGNORECASE)) is not None:
        anyp = any_number_part(any_n[1], 0)
        return AbilityCost(components=(anyp,)) if anyp is not None else None
    if text.lower().startswith("you may") or "," in text:
        return None
    has_x = re.search(r"\bx\b", text, re.IGNORECASE) is not None  # -- X sized by a count (wave 25D) -- one part sized by the announced X (below)
    if has_x and not re.match(r"^(?:(?:sacrifice|discard|exile|return) X |blight X$)", text, re.IGNORECASE) and text != "sacrifice an artifact or creature with mana value X":  # (wave 110O: Nahiri's Sacrifice)
        return None
    parts = [p.strip() for p in re.split(r" and (?=(?:sacrifice|discard|pay|exile|return|tap) )", text)]
    components: list[CostComponent] = []
    for part in parts:
        found = _component(part[:1].upper() + part[1:], "") or _exile_to_gy(part[:1].upper() + part[1:]) \
            or _extra_part(part[:1].upper() + part[1:])
        if found is None:
            # A spell can pay counters from other permanents, never from its own
            # off-battlefield source. Keep variable/optional counter costs refused.
            counter_part = _one_4h(part[:1].upper() + part[1:], "")
            if (counter_part is not None and counter_part.kind == REMOVE_COUNTER
                    and counter_part.selector is not None
                    and (counter_part.among or part.lower() == "remove a counter from a creature you control")
                    and not counter_part.x and not counter_part.more and counter_part.amount > 0):
                components.append(counter_part)
                continue
        if found is None and part.lower() == "discard your hand":  # -- (wave 110M) -- 701.9a: every card in the hand (none is fine)
            found = _one_4h("Discard your hand", "")
        if found is None and has_x:  # (the part sized by X, 107.3a: one only — "discard X cards and sacrifice X creatures" isn't read)
            found = _one_4h(part[:1].upper() + part[1:], "")
            if found is None or not found.x or len(parts) != 1:
                return None
        if found is None or found.kind not in _ADDITIONAL_KINDS:
            return None
        if found.selector is None and found.kind not in (PAY_LIFE, PAY_ENERGY, FORAGE, DISCARD_HAND):
            return None
        components.append(found)
    return AbilityCost(components=tuple(components), life=sum(c.amount for c in components if c.kind == PAY_LIFE))


# -- static wordings (wave 6E) -- a choice between additional costs (601.2b: announced as the spell is cast; 601.2f: the
# chosen one is part of the total cost): "sacrifice an artifact or discard a card", "discard a card or pay 3 life",
# "sacrifice a creature or pay {3}{B}" (a mana branch is paid with the mana cost). Each side must be a cost the grammar
# pays by itself; "reveal …", "behold …", "blight …", "forage" sides stay manual.
_EITHER_SPLIT = re.compile(r" or (?=(?:sacrifice|discard|pay|exile|return|tap) )")
_EITHER_LIST = re.compile(r",(?: or)? (?=(?:sacrifice|discard|pay|exile|return|tap) )")
_PAY_MANA = re.compile(r"^pay (?P<mana>(?:\{(?:\d+|[WUBRGC]|[WUBRG2]/[WUBRGP])\})+)$")
EITHER_SLOT = 20  # (the cost choice that names the chosen side: "either:<i>", A.CostChoice.component's last index)


def _either(text: str) -> AbilityCost | None:
    """None: not a choice; AbilityCost(either=()) a choice the grammar can't pay; else the sides."""
    sides = (_EITHER_LIST if ", or " in text else _EITHER_SPLIT).split(text)  # (wave 100D: "sacrifice a creature, discard a card, or pay 4 life", Dusk Mangler)
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
