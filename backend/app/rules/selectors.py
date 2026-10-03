"""A generic selector for objects, cards and players (CR 109, 115, 700.x "you control" etc.).

Oracle noun phrases — "nonland permanent an opponent controls", "creature card with mana value 3
or less from your graveyard", "another untapped Goblin you control", "artifact or enchantment",
"creature with power 2 or less", "opponent" — are parsed by one small grammar into a ``Selector``:

* what kind of thing: a permanent/spell/card (``types`` any-of, ``subtypes`` any-of, ``supertypes``),
  or a player (``player`` = "any" / "opponent" / "you");
* where: ``zones`` (battlefield, graveyard, hand, exile, library, stack, command) and whose zone;
* relations: controller / owner (including "defending player controls", CR 508.5), another (not
  the source), tapped, attacking, blocking, "attacking or blocking" (in combat), token, commander,
  enchanted/equipped;
* characteristics: colors, colorless, multicolored, mana value / power / toughness comparisons,
  keyword abilities it has or lacks, negated types ("nonland", "non-Human").

A selector is data. It's stored as a canonical string ``"sel:{json}"`` so it can live wherever a
selector key lives (target specs on the stack, saves), and evaluated with :func:`matches`.
Anything the grammar doesn't understand makes the parse fail (None): never a guess.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, replace
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from app.rules.creature_types import CREATURE_TYPES

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

PREFIX = "sel:"
CARD_TYPES = {"artifact": "Artifact", "creature": "Creature", "enchantment": "Enchantment", "land": "Land",
              "planeswalker": "Planeswalker", "battle": "Battle", "instant": "Instant", "sorcery": "Sorcery",
              "kindred": "Kindred"}
PERMANENT_TYPES = ("Artifact", "Creature", "Enchantment", "Land", "Planeswalker", "Battle")
SUPERTYPES = {"legendary": "Legendary", "basic": "Basic", "snow": "Snow"}
COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
KEYWORDS = ("flying", "first strike", "double strike", "deathtouch", "lifelink", "vigilance", "trample", "haste",
            "reach", "menace", "indestructible", "hexproof", "defender", "shroud", "flash", "protection")
# Noncreature subtypes that appear in selectors (205.3g-k).
OTHER_SUBTYPES = {"Equipment", "Aura", "Vehicle", "Food", "Clue", "Treasure", "Blood", "Gold", "Saga", "Shrine",
                  "Curse", "Plains", "Island", "Swamp", "Mountain", "Forest", "Desert", "Gate", "Cave", "Town",
                  "Sphere", "Lesson", "Adventure", "Arcane", "Trap", "Room", "Class", "Case", "Background",
                  "Fortification", "Attraction", "Contraption", "Powerstone", "Map", "Incubator", "Junk",
                  "Lair"}  # (Lair: the Dragon's Lair lands, "return a non-Lair land you control", wave 1B)
# -- kicked / instead (wave 4G) -- 205.3j: the planeswalker types ("If you control a Jace planeswalker, …"), read only
# when written capitalized (a word like "will" is never one)
PLANESWALKER_TYPES = frozenset({
    "Ajani", "Aminatou", "Angrath", "Arlinn", "Ashiok", "Bahamut", "Basri", "Bolas", "Calix", "Chandra", "Comet",
    "Dack", "Dakkon", "Daretti", "Davriel", "Dellian", "Dihada", "Domri", "Dovin", "Ellywick", "Elminster",
    "Elspeth", "Estrid", "Freyalise", "Garruk", "Gideon", "Grist", "Guff", "Huatli", "Jace", "Jared", "Jaya",
    "Jeska", "Kaito", "Karn", "Kasmina", "Kaya", "Kiora", "Koth", "Liliana", "Lolth", "Lukka", "Minsc",
    "Mordenkainen", "Nahiri", "Narset", "Niko", "Nissa", "Nixilis", "Oko", "Quintorius", "Ral", "Rowan", "Saheeli",
    "Samut", "Sarkhan", "Serra", "Sivitri", "Sorin", "Szat", "Tamiyo", "Tasha", "Teferi", "Teyo", "Tezzeret",
    "Tibalt", "Tyvar", "Ugin", "Urza", "Venser", "Vivien", "Vraska", "Vronos", "Will", "Windgrace", "Wrenn",
    "Xenagos", "Yanggu", "Yanling", "Zariel"
})
_IRREGULAR = {"elves": "Elf", "dwarves": "Dwarf", "wolves": "Wolf", "werewolves": "Werewolf", "thieves": "Thief",
              "mice": "Mouse", "fungi": "Fungus", "sphinxes": "Sphinx", "foxes": "Fox", "djinn": "Djinn",
              "allies": "Ally", "fairies": "Faerie", "zombies": "Zombie", "sorceries": "Sorcery", "mercenaries": "Mercenary",
              "plains": "Plains", "pegasi": "Pegasus", "octopi": "Octopus", "harpies": "Harpy", "dryads": "Dryad"}
_MARKERS = {"card", "spell", "perm", "token", "commander"}  # nouns that mark what kind of object, not its type
ZONES = ("battlefield", "graveyard", "hand", "exile", "library", "stack", "command")


@dataclass(frozen=True)
class Selector:
    player: str | None = None  # a player selector: "any" | "opponent" | "you"
    zones: tuple[str, ...] = ("battlefield",)
    zone_owner: str | None = None  # "you" | "opponent": whose graveyard / hand / library
    card: bool = False  # "… card" (not on the battlefield or stack)
    types: tuple[str, ...] = ()  # any of these card types (empty: any permanent / card)
    not_types: tuple[str, ...] = ()
    subtypes: tuple[str, ...] = ()  # any of these subtypes
    not_subtypes: tuple[str, ...] = ()
    supertypes: tuple[str, ...] = ()
    not_supertypes: tuple[str, ...] = ()
    controller: str | None = None  # "you" | "opponent" | "defending" (the defending player, 508.5)
    owner: str | None = None  # "you" | "opponent"
    other: bool = False  # "another" / "other": not the source object
    tapped: bool | None = None
    attacking: bool = False
    blocking: bool = False
    in_combat: bool = False  # "attacking or blocking" (506.3: only creatures attack or block)
    token: bool | None = None
    commander: bool = False
    colors: tuple[str, ...] = ()  # any of these colors
    not_colors: tuple[str, ...] = ()
    colorless: bool | None = None
    multicolored: bool | None = None
    with_keywords: tuple[str, ...] = ()
    without_keywords: tuple[str, ...] = ()
    compare: tuple[tuple[str, str, int], ...] = ()  # ("mv"|"power"|"toughness", "<="|">="|"==", n)
    # "enchanted", "equipped", "counter:+1/+1", "all_types", "attacking_you", "single_graveyard"
    # (a group constraint: every target from one graveyard — read by language.target_group)
    extras: tuple[str, ...] = field(default_factory=tuple)
    # -- target forms (agent T) --
    # "creature or Vehicle": the types and the subtypes are alternatives (either matches), not both
    union: bool = False
    # an activated or triggered ability on the stack (115.1c-d, 115.2b: "target activated or
    # triggered ability"): "any" | "activated" | "triggered". Mana abilities never use the stack.
    ability: str | None = None

    def key(self) -> str:
        """Canonical and compact: only fields that differ from the defaults."""
        base = asdict(_DEFAULT)
        data = {k: v for k, v in asdict(self).items() if v != base[k]}
        return PREFIX + json.dumps(data, separators=(",", ":"), sort_keys=True)


_DEFAULT = Selector()


def is_plural(phrase: str) -> bool:
    """Does the phrase name a group ("creatures you control", "other Elves")? (its head noun is plural)"""
    for word in phrase.replace(",", " ").split():
        if _core(word) is not None and _singular(word) != word:
            return True
    return False


def from_key(key: str) -> Selector:
    return _from_key(key)


@lru_cache(maxsize=4096)
def _from_key(key: str) -> Selector:
    data = json.loads(key[len(PREFIX):])
    fields: dict[str, Any] = {}
    for k, v in data.items():  # JSON lists back to (nested) tuples
        fields[k] = tuple(tuple(x) if isinstance(x, list) else x for x in v) if isinstance(v, list) else v
    return Selector(**fields)


# -- parsing ------------------------------------------------------------------------------
_NUM = r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten|x)"
_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


X_VALUE = -1  # a comparison with X: the X of the spell (or ability) the selector is read for (107.3f, 202.3e)


def _n(word: str) -> int | None:
    if word.isdigit():
        return int(word)
    return _NUMBERS.get(word.lower())


_SUFFIXES: list[tuple[re.Pattern[str], Any]] = []


def _in_zone(s: Selector, zone: str, owner: str | None) -> Selector:
    """A zone suffix ("from your graveyard"): two different zones is a phrase we don't understand."""
    if s.zones != _DEFAULT.zones and (s.zones != (zone,) or s.zone_owner != owner):
        raise ValueError("conflicting zones")
    return replace(s, zones=(zone,), zone_owner=owner, card=True)


def _suffix(pattern: str):  # type: ignore[no-untyped-def]
    def register(fn):  # type: ignore[no-untyped-def]
        _SUFFIXES.append((re.compile(r"(?:,)? " + pattern + r"$"), fn))
        return fn
    return register


@_suffix(r"(?:that )?you control")
def _you_control(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, controller="you")


@_suffix(r"(?:that )?(?:an opponent controls|your opponents control|you don't control|you don’t control)")
def _opp_control(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, controller="opponent")


@_suffix(r"(?:that )?defending player controls")
def _defending_controls(s: Selector, m: re.Match[str]) -> Selector:
    # 508.5: the defending player an attacking creature's ability refers to is the player (or
    # the controller of the planeswalker) it's attacking; 508.5a: one specific defending player.
    return replace(s, controller="defending")


@_suffix(r"other than ~")
def _other_than_self(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, other=True)


@_suffix(r"that['’]s (?P<w>attacking or blocking|attacking|blocking|tapped|untapped)")
def _thats_status(s: Selector, m: re.Match[str]) -> Selector:
    s2 = _prefix(s, m["w"].replace(" ", "-"))
    assert s2 is not None
    return s2


@_suffix(r"that attacked this turn")  # -- combat (wave 5C) -- declared as attackers this turn (508.1; 508.4: not put)
def _attacked_this_turn(s: Selector, m: re.Match[str]) -> Selector:
    if not m.string[: m.start()].endswith("creatures"):
        raise ValueError("only \"creatures that attacked this turn\" (a group on the battlefield)")
    return replace(s, extras=(*s.extras, "attacked_this_turn"))


@_suffix(r"that['’]s attacking you")
def _attacking_you(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, attacking=True, extras=(*s.extras, "attacking_you"))


@_suffix(r"that['’]s (?P<c1>" + "|".join(COLORS) + r")(?: or (?P<c2>" + "|".join(COLORS) + r"))?")
def _thats_colored(s: Selector, m: re.Match[str]) -> Selector:
    found = tuple(COLORS[c] for c in (m["c1"], m["c2"]) if c)
    return replace(s, colors=(*s.colors, *found))


@_suffix(r"that['’]s one or more colors")
def _thats_colors(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, colorless=False)


@_suffix(r"you own")
def _you_own(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, owner="you")


@_suffix(r"(?:an opponent owns|you don't own)")
def _opp_own(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, owner="opponent")


@_suffix(r"(?:from|in) your (?P<z>graveyard|hand|library)")
def _your_zone(s: Selector, m: re.Match[str]) -> Selector:
    return _in_zone(s, m["z"], "you")


@_suffix(r"(?:from|in) (?:a|any) graveyard")
def _any_graveyard(s: Selector, m: re.Match[str]) -> Selector:
    return _in_zone(s, "graveyard", None)


@_suffix(r"(?:from|in) an opponent's graveyard")
def _opp_graveyard(s: Selector, m: re.Match[str]) -> Selector:
    return _in_zone(s, "graveyard", "opponent")


@_suffix(r"(?:from|in) graveyards")
def _graveyards(s: Selector, m: re.Match[str]) -> Selector:
    return _in_zone(s, "graveyard", None)  # any graveyards (400.1: each player has their own)


@_suffix(r"from all graveyards")  # -- reanimation (wave 3R) --
def _all_graveyards(s: Selector, m: re.Match[str]) -> Selector:
    return _in_zone(s, "graveyard", None)


@_suffix(r"from a single graveyard")
def _single_graveyard(s: Selector, m: re.Match[str]) -> Selector:
    """"Exile up to two target cards from a single graveyard": any graveyard, but all the targets
    from the same one (400.1: a player's graveyard is theirs — the same owner). The constraint
    is on the group of targets, not on one card: language.target_group moves it to the group."""
    return replace(_in_zone(s, "graveyard", None), extras=(*s.extras, "single_graveyard"))


@_suffix(r"(?:from|in) exile")
def _exile(s: Selector, m: re.Match[str]) -> Selector:
    return _in_zone(s, "exile", None)


@_suffix(r"with (?P<what>mana value|power|toughness) " + _NUM.replace("|x)", "|[xX])") + r" or (?P<dir>less|greater|more)")
def _compare(s: Selector, m: re.Match[str]) -> Selector:
    n = _n(m.group(2))
    if n is None and m["what"] == "mana value" and m.group(2).lower() == "x" and m["dir"] == "less":
        n = X_VALUE  # -- control (wave 3K) -- "target creature with mana value X or less" (Dominate): the X of the spell
    if n is None:
        raise ValueError("X comparisons need a value")
    what = {"mana value": "mv", "power": "power", "toughness": "toughness"}[m["what"]]
    return replace(s, compare=(*s.compare, (what, "<=" if m["dir"] == "less" else ">=", n)))


@_suffix(r"with (?P<what>mana value|power|toughness) " + _NUM)
def _equal(s: Selector, m: re.Match[str]) -> Selector:
    n = _n(m.group(2))
    if n is None:
        raise ValueError("X comparisons need a value")
    what = {"mana value": "mv", "power": "power", "toughness": "toughness"}[m["what"]]
    return replace(s, compare=(*s.compare, (what, "==", n)))


@_suffix(r"with (?P<kw>" + "|".join(KEYWORDS) + r")")
def _with_kw(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, with_keywords=(*s.with_keywords, m["kw"]))


@_suffix(r"without (?P<kw>" + "|".join(KEYWORDS) + r")")
def _without_kw(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, without_keywords=(*s.without_keywords, m["kw"]))


@_suffix(r"with an? (?P<c>\+1/\+1|-1/-1|[a-z]+) counter on it")
def _with_counter(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, f"counter:{m['c']}"))


# -- counters (wave 5H) -- "creatures you control with +1/+1 counters on them", "each creature you control with a
# counter on it" (any kind, 122.1), "creatures with no counters on them", "each creature without a +1/+1 counter on
# it", "each nonland permanent without a fate counter on it", "a creature that has a +1/+1 counter on it"
_CK = r"(?:(?!no |one |any |more )(?P<c>\+1/\+1|-1/-1|[a-z]+) )?"


@_suffix(r"(?:with (?:an? |one or more )?|that (?:has|have) (?:an? |one or more )?)" + _CK + r"counters? on (?:it|them)")
def _with_counters(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, f"counter:{m['c'] or COUNTER_ANY}"))


@_suffix(r"(?:with no |without (?:an? |any )?)" + _CK + r"counters? on (?:it|them)")
def _without_counters(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, f"nocounter:{m['c'] or COUNTER_ANY}"))


COUNTER_ANY = "*"


def _has_counter(card: CardInstance, kind: str) -> bool:
    if kind == COUNTER_ANY:
        return any(v > 0 for v in card.counters.values())
    return card.counters.get(kind, 0) > 0
# -- end counters (wave 5H) --


# -- chosen type (wave 4J) ------------------------------------------------------------------------------------------
# "creatures you control of the chosen type", "a spell of the chosen color", "creatures that aren't of the chosen
# type": the creature type (205.3m) / color (105.1) chosen for the source — as it entered ("As ~ enters, choose a
# creature type": its public "Chosen creature type" record, 614.12a), or earlier in the same resolution ("Choose a
# creature type. Destroy all creatures that aren't of the chosen type": bind_chosen substitutes that answer).
# ``matches`` reads the source's record; without a source or a valid record nothing matches (never a guess).
CHOSEN_EXTRAS = {"chosen_type": "creature type", "chosen_color": "color", "not_chosen_type": "creature type",
                 "not_chosen_color": "color"}


@_suffix(r"(?P<neg>that (?:aren't|isn't|are not|is not) )?of the chosen (?P<what>type|color)")
def _of_chosen(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, ("not_" if m["neg"] else "") + f"chosen_{m['what']}"))


def chosen_what(sel: Selector) -> str | None:
    """"creature type" / "color" when the selector reads a chosen value, else None."""
    found = {CHOSEN_EXTRAS[e] for e in sel.extras if e in CHOSEN_EXTRAS}
    return found.pop() if len(found) == 1 else None


def bind_chosen(sel: Selector, value: str) -> Selector | None:
    """The selector with the chosen value put in place (``value``: "Elf", "Blue"); None if the value isn't one."""
    rest = tuple(e for e in sel.extras if e not in CHOSEN_EXTRAS)
    what = chosen_what(sel)
    neg = any(e.startswith("not_") for e in sel.extras if e in CHOSEN_EXTRAS)
    if what == "creature type" and value in CREATURE_TYPES:
        if sel.subtypes or sel.not_subtypes or sel.union:
            return None
        if neg:
            return replace(sel, extras=rest, not_subtypes=(value,))
        return replace(sel, extras=rest, subtypes=(value,))
    color = COLORS.get(value.strip().lower())
    if what == "color" and color is not None:
        if sel.colors or sel.not_colors:
            return None
        if neg:
            return replace(sel, extras=rest, not_colors=(color,))
        return replace(sel, extras=rest, colors=(color,))
    return None


def source_choice(plan: Plan, source: str | None, what: str) -> str | None:
    """The source permanent's recorded "As ~ enters, choose a creature type / a color" answer (its public
    ``choices`` entry), or None."""
    card = plan.state.cards.get(source or "")
    if card is None:
        return None
    label = {"creature type": "Chosen creature type", "color": "Chosen color"}[what]
    value = card.choices.get(label)
    return value.strip() if value else None


def _chosen_ok(plan: Plan, sel: Selector, ch: Characteristics, source: str | None) -> bool:
    what = chosen_what(sel)
    value = source_choice(plan, source, what) if what is not None else None
    bound = bind_chosen(sel, value) if value is not None else None
    if bound is None:
        return False
    if bound.subtypes and not set(bound.subtypes) & ch.subtypes:
        return False
    if set(bound.not_subtypes) & ch.subtypes:
        return False
    if bound.colors and not set(bound.colors) & ch.colors:
        return False
    return not set(bound.not_colors) & ch.colors
# -- end chosen type (wave 4J) --------------------------------------------------------------------------------------


def _singular(word: str) -> str:
    low = word.lower()
    if low in _IRREGULAR:
        return _IRREGULAR[low]
    if low.endswith("ies") and low[:-3] + "y" in {"ally", "fairy"}:
        return low[:-3] + "y"
    if low.endswith("es") and low[:-2] in ("sorceri", "wolv"):
        return low[:-2]
    if low.endswith("s") and not low.endswith("ss"):
        return word[:-1]
    return word


def _core(word: str) -> tuple[str, str] | None:
    """One noun of the core: ("type", "Creature") / ("sub", "Goblin") / ("perm", "") / ("card", "") …"""
    w = _singular(word)
    low = w.lower()
    if low in CARD_TYPES:
        return "type", CARD_TYPES[low]
    if low == "permanent":
        return "perm", ""
    if low == "spell":
        return "spell", ""
    if low == "card":
        return "card", ""
    if low == "token":  # "creature token", "token you control", "Incubator token" (111.1)
        return "token", ""
    if low == "commander":  # "target commander", "commander you own" (903.3)
        return "commander", ""
    if low in ("player", "opponent"):
        return "player", low
    cap = w[:1].upper() + w[1:]
    if cap in CREATURE_TYPES or cap in OTHER_SUBTYPES:
        return "sub", cap
    if word[:1].isupper() and word in PLANESWALKER_TYPES:  # -- kicked / instead (wave 4G) -- 205.3j
        return "sub", word
    return None


def _prefix(s: Selector, word: str) -> Selector | None:
    low = word.lower()
    if low in ("another", "other"):
        return replace(s, other=True)
    if low in ("tapped", "untapped"):
        return replace(s, tapped=low == "tapped")
    if low == "attacking":
        return replace(s, attacking=True)
    if low == "blocking":
        return replace(s, blocking=True)
    if low in ("attacking-or-blocking", "blocking-or-attacking"):  # (joined by parse: one status)
        return replace(s, in_combat=True)
    pt = re.fullmatch(r"(\d+)/(\d+)", word)
    if pt:  # "1/1 creature": exactly that power and toughness
        return replace(s, compare=(*s.compare, ("power", "==", int(pt[1])), ("toughness", "==", int(pt[2]))))
    if low == "token":
        return replace(s, token=True)
    if low == "nontoken":
        if s.token is True:
            return None  # ("nontoken token")
        return replace(s, token=False)
    if low in SUPERTYPES:
        return replace(s, supertypes=(*s.supertypes, SUPERTYPES[low]))
    if low.startswith("non") and low[3:] in SUPERTYPES:
        return replace(s, not_supertypes=(*s.not_supertypes, SUPERTYPES[low[3:]]))
    if low in COLORS:
        return replace(s, colors=(*s.colors, COLORS[low]))
    if low == "colorless":
        return replace(s, colorless=True)
    if low == "multicolored":
        return replace(s, multicolored=True)
    if low == "monocolored":
        return replace(s, multicolored=False, colorless=False)
    if low == "commander":
        return replace(s, commander=True)
    if low in ("enchanted", "equipped"):
        return replace(s, extras=(*s.extras, low))
    if low in ("face-down", "face-up"):  # -- keyword actions & face-down (wave 3F) -- 708: "face-down creatures you control"
        return replace(s, extras=(*s.extras, low.replace("-", "_")))
    if low.startswith("non"):
        rest = word[4:] if word[3:4] == "-" else word[3:]
        if rest.lower() in COLORS:
            return replace(s, not_colors=(*s.not_colors, COLORS[rest.lower()]))
        core = _core(rest)
        if core is None:
            return None
        if core[0] == "type":
            return replace(s, not_types=(*s.not_types, core[1]))
        if core[0] == "sub":
            return replace(s, not_subtypes=(*s.not_subtypes, core[1]))
        return None
    return None


_ABILITY = re.compile(r"(?P<kind>activated or triggered|activated|triggered) abilit(?:y|ies)")
# -- stack interaction (wave 5B) -- "spell or ability" / "spell, activated ability, or triggered ability": any object on
# the stack (a mana ability never is one, 605.3a), ``ability`` "spell_or_ability"; "… with a single target": a spell or
# ability that has exactly one target (its stack entry's target positions: Shunt, Imp's Mischief — the rulings: one
# that targets several things, or one thing several times, isn't one)
SPELL_OR_ABILITY = "spell_or_ability"
_SPELL_OR_ABILITY = re.compile(r"spell or ability|spell, activated ability, or triggered ability")


@_suffix(r"with a single target")
def _single_target(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "single_target"))


def _targets_suffix(s: Selector, m: re.Match[str]) -> Selector:
    """"… that targets you / a permanent you control / you or a creature you control / this creature": a spell or
    ability one of whose targets is that (Rebuff the Wicked's and Siren Stormtamer's rulings: one of several is enough;
    a targeted permanent must still be on the battlefield and match now, whether or not it's still a legal target for
    that spell). Encoded as the extra "targets:<you>|<selector key or self>"."""
    what = m["w"].strip()
    you = what == "you" or what.startswith("you or ")
    rest = what[len("you or "):] if what.startswith("you or ") else ("" if what == "you" else what)
    if rest in ("this creature", "~"):
        key = "self"
    elif rest:
        art = re.fullmatch(r"(?:a|an) (?P<p>.+)", rest)
        sub = parse(art["p"]) if art is not None else None
        if sub is None or sub.zones != ("battlefield",) or sub.player is not None or sub.extras or sub.ability is not None:
            if art is not None and art["p"] == "player" and not you:
                return replace(s, extras=(*s.extras, "targets:player|"))
            raise ValueError("unread target condition")
        key = sub.key()
    else:
        key = ""
    return replace(s, extras=(*s.extras, f"targets:{'you' if you else ''}|{key}"))


_SUFFIXES.insert(0, (re.compile(r" that targets (?P<w>(?!only\b).+)$"), _targets_suffix))


def targets_match(plan: Plan, card: CardInstance, extra: str, you: str, source: str | None) -> bool:
    """Does this spell or ability on the stack target what the "targets:" extra names?"""
    entry = plan.rules.stack.get(card.id) if plan.rules is not None else None
    if entry is None:
        return False
    players, _, key = extra[len("targets:"):].partition("|")
    for t in entry.targets:
        if t.id in plan.state.players:
            if (players == "you" and t.id == you) or players == "player":
                return True
            continue
        target = plan.state.cards.get(t.id)
        if not key or target is None or not target.zone.endswith(":battlefield") or plan.oid(target) != t.object_id:
            continue  # (one that left isn't "a permanent you control" any more: 400.7)
        if key == "self":
            if target.id == source:
                return True
        elif matches(plan, from_key(key), target, plan.ch(target), you, source):
            return True
    return False


def single_target(plan: Plan, card: CardInstance) -> bool:
    from app.rules import copying  # (copying imports this module)

    entry = plan.rules.stack.get(card.id) if plan.rules is not None else None
    return entry is not None and len(copying.positions(entry)) == 1
# -- end stack interaction (wave 5B) --


def parse(phrase: str) -> Selector | None:
    """A noun phrase without its determiner ("nonland permanent an opponent controls") → Selector."""
    return _parse(phrase.strip())


@lru_cache(maxsize=8192)
def _parse(phrase: str) -> Selector | None:
    s = Selector()
    text = phrase
    qualified = False  # a "with …" / "without …" qualifier
    try:
        changed = True
        while changed:
            changed = False
            for pattern, fn in _SUFFIXES:
                m = pattern.search(text)
                if m:
                    s = fn(s, m)
                    qualified = qualified or m.group(0).lstrip().startswith(("with ", "without "))
                    text = text[: m.start()]
                    changed = True
                    break
    except ValueError:
        return None
    if qualified and re.search(r", or \S+$", text):
        # "artifact, enchantment, or creature with flying": the qualifier is the last item's
        # only (any artifact; a creature with flying), which a selector can't say: not a guess
        return None
    # -- recursion & tutors (wave 4M) -- "Angel or Human creature card" (Bruna, the Fading Light): subtypes any of which
    # matches, narrowing one card type (205.3); "historic card" (700.6: legendary, artifact or Saga)
    if text.strip() in ("historic card", "historic cards") and not qualified:
        return replace(s, card=True, zones=() if s.zones == ("battlefield",) else s.zones, extras=(*s.extras, "historic"))
    alt_subs = re.fullmatch(r"(?P<subs>[A-Z][\w'’-]*(?:,? or [A-Z][\w'’-]*)+) (?P<rest>(?:creature|artifact|enchantment|land|planeswalker) cards?)",
                            text.strip())
    if alt_subs is not None:
        subs = [_core(w) for w in re.split(r",? or ", alt_subs["subs"])]
        base = _parse(alt_subs["rest"]) if all(c is not None and c[0] == "sub" for c in subs) else None
        if base is None or base.subtypes or base.union or len(base.types) != 1 or not base.card:
            return None
        return replace(s, card=True, zones=() if s.zones == ("battlefield",) else s.zones, types=base.types,
                       subtypes=tuple(dict.fromkeys(c[1] for c in subs if c is not None)))
    # -- end recursion & tutors (wave 4M) --
    words = text.replace(",", " ,").split()
    if not words:
        return None
    ability =_ABILITY.fullmatch(text.strip())
    if ability is not None:  # -- target forms (agent T) --
        if s.zones != _DEFAULT.zones or s.owner is not None or s.controller not in (None, "you", "opponent"):
            return None  # ("ability from an artifact source": its source's qualities aren't read)
        kind = {"activated or triggered": "any", "activated": "activated", "triggered": "triggered"}[ability["kind"]]
        return replace(s, zones=("stack",), ability=kind)
    if _SPELL_OR_ABILITY.fullmatch(text.strip()):  # -- stack interaction (wave 5B) --
        if s.zones != _DEFAULT.zones or s.owner is not None or s.controller not in (None, "you", "opponent"):
            return None
        return replace(s, zones=("stack",), ability=SPELL_OR_ABILITY)
    # The core: the trailing nouns. Joined by "or" / "," they're alternatives ("artifact or
    # enchantment"); side by side they narrow each other ("artifact creature", "Goblin creature").
    nouns: list[tuple[str, str]] = []
    joins: set[str] = set()
    i = len(words) - 1
    pending_join = ""
    while i >= 0:
        w = words[i]
        if w in (",", "or", "and/or"):
            pending_join = "or"
            i -= 1
            continue
        c = _core(w)
        if c is None:
            break
        if nouns and pending_join and _MARKERS & {c[0], nouns[-1][0]}:
            return None  # "spell or permanent", "creature card or planeswalker": a union we can't express
        if nouns and nouns[-1][0] not in _MARKERS:  # ("creature card": card marks the zone)
            joins.add(pending_join or "and")
        nouns.append(c)
        pending_join = ""
        i -= 1
    if pending_join or not nouns:
        return None
    kinds = [c for c in nouns if c[0] not in _MARKERS]
    markers = {c[0] for c in nouns} - {"type", "sub", "player"}
    if any(k[0] == "player" for k in kinds):
        if len(nouns) != 1 or i >= 0 or s != _DEFAULT:  # ("player from your graveyard")
            return None
        return Selector(player="opponent" if kinds[0][1] == "opponent" else "any")
    types = tuple(dict.fromkeys(v for k, v in kinds if k == "type"))
    subtypes = tuple(dict.fromkeys(v for k, v in kinds if k == "sub"))
    if "or" in joins and "and" in joins:
        return None  # "artifact creature or enchantment": not yet
    union = False
    if "or" in joins and types and subtypes:
        union = True  # "creature or Vehicle": either kind matches (-- target forms (agent T) --)
    if "spell" in markers:
        if "card" in markers or s.zones != _DEFAULT.zones:
            return None  # "spell from your graveyard" (cast from a graveyard): not a selector
        s = replace(s, zones=("stack",))
    if "card" in markers:
        s = replace(s, card=True)
        if s.zones == ("battlefield",):
            s = replace(s, zones=())  # "a creature card": the zone comes from the sentence
    if "token" in markers:
        if s.card or "spell" in markers or s.token is False:
            return None  # ("token card": no such thing; a token is only ever a permanent, 111.7)
        s = replace(s, token=True)
    if "commander" in markers:
        if s.card or "spell" in markers:
            return None  # (a commander card in the command zone / a commander spell: not yet)
        s = replace(s, commander=True)
    if "perm" in markers and not types and (s.card or "spell" in markers):
        # "permanent card" (110.4a) / "permanent spell" (110.4b): only the permanent types, any of
        # them — so an instant, a sorcery or a kindred sorcery doesn't match. (On the battlefield,
        # matches() already requires a permanent type.)
        types = PERMANENT_TYPES if s.card else tuple(t for t in PERMANENT_TYPES if t != "Land")
    if "and" in joins and len(types) > 1:
        s = replace(s, types=types, extras=(*s.extras, "all_types"))  # "artifact creature"
    else:
        s = replace(s, types=types)
    s = replace(s, subtypes=subtypes, union=union)
    prefix_words = _join_statuses(words[: i + 1])
    for k, w in enumerate(reversed(prefix_words)):
        if w in (",",):
            continue
        if w in ("or", "and"):  # "black or red", "white and/or blue": colors are alternatives
            j = len(prefix_words) - 1 - k
            if 0 < j < len(prefix_words) - 1 and prefix_words[j - 1].lower() in COLORS \
                    and prefix_words[j + 1].lower() in COLORS and w == "or":
                continue
            return None
        s2 = _prefix(s, w)
        if s2 is None:
            return None
        s = s2
    return s


def _join_statuses(words: list[str]) -> list[str]:
    """"attacking or blocking creature": the two words are one status (either), not two
    prefixes that both apply (an attacking creature that's also blocking)."""
    out: list[str] = []
    k = 0
    while k < len(words):
        if k + 2 < len(words) and words[k + 1] == "or" and {words[k].lower(), words[k + 2].lower()} == {"attacking", "blocking"}:
            out.append("attacking-or-blocking")
            k += 3
            continue
        out.append(words[k])
        k += 1
    return out


# -- evaluation ---------------------------------------------------------------------------
def _defender(plan: Plan, target: Any) -> str | None:
    """The player a creature is attacking, or the controller of the planeswalker it's attacking
    (508.5, 506.2: a planeswalker is attacked on its controller's behalf). Battles aren't
    modelled as attack targets: the defending player relative to a battle would be its
    *protector*, not its controller (310.9d) — not invented here."""
    if target is None:
        return None
    if target.kind == "player":
        return str(target.id)
    attacked = plan.state.cards.get(target.id)
    if attacked is None or not attacked.zone.endswith(":battlefield"):
        return None
    return attacked.controller


def attacker_of(event: Any) -> str | None:
    """The attacking creature an "attacks" trigger event is about (its card id), from the
    TriggerEvent (a model, or its JSON in a resolution context); None for any other event."""
    if event is None:
        return None
    kind = event.get("kind") if isinstance(event, dict) else getattr(event, "kind", None)
    if kind != "attack":
        return None
    objects = event.get("objects") if isinstance(event, dict) else getattr(event, "objects", None)
    if not objects:
        return None
    first = objects[0]
    card = first.get("card") if isinstance(first, dict) else getattr(first, "card", None)
    return str(card) if card else None


def defending_players(plan: Plan, source: str | None, attacker: str | None = None) -> set[str]:
    """Who "defending player" means (508.5): the player the creature in question is attacking
    (or whose planeswalker it's attacking) — ``attacker`` for an "attacks" trigger (the event's
    creature, which may not be the ability's source: "Whenever a creature you control attacks",
    508.5a determines it for each attacking creature), else the source itself when it is
    attacking. With neither — a source that isn't attacking and no attack event — the rule would
    let the ability's controller pick one defending player (508.5a); that choice isn't modelled:
    nothing matches. Empty outside combat."""
    creature = plan.state.cards.get(attacker or source or "")
    if creature is None or creature.attacking is None:
        return set()
    d = _defender(plan, creature.attacking)
    return {d} if d else set()


def matches_player(plan: Plan, sel: Selector, pid: str, you: str) -> bool:
    if sel.player is None or pid not in plan.live():
        return False
    if sel.player == "opponent":
        return pid != you
    if sel.player == "you":
        return pid == you
    return True


def matches(plan: Plan, sel: Selector, card: CardInstance, ch: Characteristics, you: str,
            source: str | None = None, attacker: str | None = None) -> bool:
    """Does this object match the selector (``you``: the player it's evaluated for; ``source``:
    the ability's source, for "another …" and "defending player"; ``attacker``: the creature an
    "attacks" trigger is about, whose defending player "defending player" then means, 508.5)?"""
    zone = card.zone.split(":")[-1] if ":" in card.zone else card.zone
    if sel.player is not None:
        return False
    if sel.zones and zone not in sel.zones:
        return False
    if not sel.zones and zone in ("battlefield", "stack"):
        return False  # "a creature card" isn't a permanent or a spell
    if sel.zone_owner == "you" and card.owner != you:
        return False
    if sel.zone_owner == "opponent" and card.owner == you:
        return False
    any_stack = sel.ability == SPELL_OR_ABILITY  # -- stack interaction (wave 5B) --
    if zone == "stack" and not any_stack and (card.ability is not None) != (sel.ability is not None):
        return False  # a spell isn't an ability, and an ability isn't a spell (115.2b)
    if sel.ability is not None and not any_stack and not _ability_kind(plan, card, sel.ability):
        return False
    if any_stack and card.ability is not None and not _ability_kind(plan, card, "any"):
        return False
    if "single_target" in sel.extras and (zone != "stack" or not single_target(plan, card)):  # (wave 5B)
        return False
    for extra in sel.extras:  # (wave 5B) "… that targets you or a creature you control"
        if extra.startswith("targets:") and (zone != "stack" or not targets_match(plan, card, extra, you, source)):
            return False
    if sel.union:  # "creature or Vehicle": either the type or the subtype (-- target forms (agent T) --)
        if not (set(sel.types) & ch.types or set(sel.subtypes) & ch.subtypes):
            return False
    elif sel.types:
        if "all_types" in sel.extras:
            if not set(sel.types) <= ch.types:
                return False
        elif not set(sel.types) & ch.types:
            return False
    elif not sel.card and zone == "battlefield" and not ch.types & set(PERMANENT_TYPES):
        return False
    if set(sel.not_types) & ch.types:
        return False
    if sel.subtypes and not sel.union and not set(sel.subtypes) & ch.subtypes:
        return False
    if set(sel.not_subtypes) & ch.subtypes:
        return False
    if sel.supertypes and not set(sel.supertypes) <= ch.supertypes:
        return False
    if set(sel.not_supertypes) & ch.supertypes:
        return False
    if sel.controller == "you" and card.controller != you:
        return False
    if sel.controller == "opponent" and card.controller == you:
        return False
    if sel.controller == "defending" and card.controller not in defending_players(plan, source, attacker):
        return False
    if sel.owner == "you" and card.owner != you:
        return False
    if sel.owner == "opponent" and card.owner == you:
        return False
    if sel.other and source is not None and card.id == source:
        return False
    if sel.tapped is not None and card.tapped != sel.tapped:
        return False
    if sel.attacking and card.attacking is None:
        return False
    if sel.blocking and not card.blocking:
        return False
    if sel.in_combat and card.attacking is None and not card.blocking:
        return False
    if sel.token is not None and card.is_token != sel.token:
        return False
    if sel.commander and card.commander_key is None:
        return False
    if sel.colors and not set(sel.colors) & ch.colors:
        return False
    if set(sel.not_colors) & ch.colors:
        return False
    if sel.colorless is not None and (not ch.colors) != sel.colorless:
        return False
    if sel.multicolored is not None and (len(ch.colors) > 1) != sel.multicolored:
        return False
    if sel.with_keywords and not set(sel.with_keywords) <= ch.keywords:
        return False
    if set(sel.without_keywords) & ch.keywords:
        return False
    for what, op, n in sel.compare:
        if n == X_VALUE:  # (107.3f: X is the one chosen for the spell; none known: nothing matches)
            src = plan.state.cards.get(source or "")
            x = src.stack_info.x if src is not None and src.stack_info is not None and src.stack_info.x is not None \
                else getattr(plan, "x_choice", None)  # (not on the stack yet: the X announced for it)
            if x is None:
                return False
            n = x
        value = _stat(ch, what)
        if what == "mv" and value is not None and zone == "stack" and card.stack_info is not None and card.stack_info.x:
            value += card.stack_info.x * ch.mana_cost.count("{X}")  # 202.3e: X on the stack is the value chosen
        if value is None or not {"<=": value <= n, ">=": value >= n, "==": value == n}[op]:
            return False
    for extra in sel.extras:
        if extra == "enchanted" and not _has_attached(plan, card, "Aura"):
            return False
        if extra == "equipped" and not _has_attached(plan, card, "Equipment"):
            return False
        # (700.6; set only by the look-and-distribute grammar: "a historic card from among them")
        if extra == "historic" and not ("Artifact" in ch.types or "Legendary" in ch.supertypes or "Saga" in ch.subtypes):
            return False
        if extra.startswith("counter:") and not _has_counter(card, extra[8:]):  # (wave 5H: any kind, "*")
            return False
        if extra.startswith("nocounter:") and _has_counter(card, extra[10:]):  # -- counters (wave 5H) --
            return False
        if extra == "attacking_you" and (card.attacking is None or card.attacking.kind != "player" or card.attacking.id != you):
            return False
        if extra in ("face_down", "face_up") and card.face_down != (extra == "face_down"):  # -- wave 3F --
            return False
        if extra == "attacked_this_turn" and not _attacked_this_turn_now(plan, card):  # -- combat (wave 5C) --
            return False
    # -- chosen type (wave 4J) --
    return not any(e in CHOSEN_EXTRAS for e in sel.extras) or _chosen_ok(plan, sel, ch, source)


def _attacked_this_turn_now(plan: Plan, card: CardInstance) -> bool:
    """-- combat (wave 5C) -- the object (400.7: not a new one) was declared as an attacker this turn (wave 4D log)."""
    r = plan.state.rules
    if r is None or r.turn_log.turn != plan.state.turn.number:
        return False
    return r.object_id(card.id) in {a for ids in r.turn_log.attackers.values() for a in ids}


def _ability_kind(plan: Plan, card: CardInstance, kind: str) -> bool:
    """Is this stack object an ability of the wanted kind ("any" / "activated" / "triggered")?
    Read from the stack entry (its rules metadata), never guessed from the text."""
    entry = plan.rules.stack.get(card.id) if plan.rules is not None else None
    actual = entry.kind if entry is not None else (card.ability.kind if card.ability is not None else None)
    if actual == "trigger":
        actual = "triggered"
    if actual not in ("activated", "triggered"):
        return False
    return kind == "any" or kind == actual


def _stat(ch: Characteristics, what: str) -> int | None:
    if what == "mv":
        return int(ch.mana_value)
    if ch.pt is not None:
        return ch.pt[0] if what == "power" else ch.pt[1]
    raw = ch.power if what == "power" else ch.toughness
    return int(raw) if raw is not None and raw.lstrip("-").isdigit() else None


def _has_attached(plan: Plan, card: CardInstance, subtype: str) -> bool:
    return any(c.attached_to == card.id and subtype in plan.ch(c).subtypes for c in plan.state.cards.values())


def candidates(plan: Plan, sel: Selector, you: str, source: str | None = None, attacker: str | None = None) -> list[str]:
    """Card ids (not players) matching the selector, in a deterministic order."""
    zones = sel.zones or ("graveyard", "hand", "exile")
    out = []
    for key, ids in plan.state.zones.items():
        zone = key.split(":")[-1]
        if zone not in zones:
            continue
        if zone in ("hand", "library") and sel.zone_owner != "you":
            continue  # hidden zones: only your own, and only when the sentence says so
        for cid in ids:
            card = plan.state.cards.get(cid)
            if card is None or not plan.in_game(card):
                continue  # 800.4a: what a player who left the game owned (or controlled) has left it too
            if matches(plan, sel, card, plan.ch(card), you, source, attacker):
                out.append(cid)
    return out
