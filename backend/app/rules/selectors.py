"""A generic selector for objects, cards and players (CR 109, 115, 700.x "you control" etc.).

Oracle noun phrases — "nonland permanent an opponent controls", "creature card with mana value 3
or less from your graveyard", "another untapped Goblin you control", "artifact or enchantment",
"creature with power 2 or less", "opponent" — are parsed by one small grammar into a ``Selector``:

* what kind of thing: a permanent/spell/card (``types`` any-of, ``subtypes`` any-of, ``supertypes``),
  or a player (``player`` = "any" / "opponent" / "you");
* where: ``zones`` (battlefield, graveyard, hand, exile, library, stack, command) and whose zone;
* relations: controller / owner, another (not the source), tapped, attacking, blocking, token,
  commander, enchanted/equipped;
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
                  "Fortification", "Attraction", "Contraption", "Powerstone", "Map", "Incubator", "Junk"}
_IRREGULAR = {"elves": "Elf", "dwarves": "Dwarf", "wolves": "Wolf", "werewolves": "Werewolf", "thieves": "Thief",
              "mice": "Mouse", "fungi": "Fungus", "sphinxes": "Sphinx", "foxes": "Fox", "djinn": "Djinn",
              "allies": "Ally", "fairies": "Faerie", "zombies": "Zombie", "sorceries": "Sorcery", "mercenaries": "Mercenary",
              "pegasi": "Pegasus", "octopi": "Octopus", "harpies": "Harpy", "dryads": "Dryad"}
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
    controller: str | None = None  # "you" | "opponent"
    owner: str | None = None  # "you" | "opponent"
    other: bool = False  # "another" / "other": not the source object
    tapped: bool | None = None
    attacking: bool = False
    blocking: bool = False
    token: bool | None = None
    commander: bool = False
    colors: tuple[str, ...] = ()  # any of these colors
    not_colors: tuple[str, ...] = ()
    colorless: bool | None = None
    multicolored: bool | None = None
    with_keywords: tuple[str, ...] = ()
    without_keywords: tuple[str, ...] = ()
    compare: tuple[tuple[str, str, int], ...] = ()  # ("mv"|"power"|"toughness", "<="|">="|"==", n)
    extras: tuple[str, ...] = field(default_factory=tuple)  # "enchanted", "equipped", "counter:+1/+1"

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


def _n(word: str) -> int | None:
    if word.isdigit():
        return int(word)
    return _NUMBERS.get(word.lower())


_SUFFIXES: list[tuple[re.Pattern[str], Any]] = []


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


@_suffix(r"you own")
def _you_own(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, owner="you")


@_suffix(r"(?:an opponent owns|you don't own)")
def _opp_own(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, owner="opponent")


@_suffix(r"(?:from|in) your (?P<z>graveyard|hand|library)")
def _your_zone(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, zones=(m["z"],), zone_owner="you", card=True)


@_suffix(r"(?:from|in) (?:a|any) graveyard")
def _any_graveyard(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, zones=("graveyard",), card=True)


@_suffix(r"(?:from|in) an opponent's graveyard")
def _opp_graveyard(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, zones=("graveyard",), zone_owner="opponent", card=True)


@_suffix(r"(?:from|in) exile")
def _exile(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, zones=("exile",), card=True)


@_suffix(r"with (?P<what>mana value|power|toughness) " + _NUM + r" or (?P<dir>less|greater|more)")
def _compare(s: Selector, m: re.Match[str]) -> Selector:
    n = _n(m.group(2))
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
    if low in ("player", "opponent"):
        return "player", low
    cap = w[:1].upper() + w[1:]
    if cap in CREATURE_TYPES or cap in OTHER_SUBTYPES:
        return "sub", cap
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
    if low == "token":
        return replace(s, token=True)
    if low == "nontoken":
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


def parse(phrase: str) -> Selector | None:
    """A noun phrase without its determiner ("nonland permanent an opponent controls") → Selector."""
    return _parse(phrase.strip())


@lru_cache(maxsize=8192)
def _parse(phrase: str) -> Selector | None:
    s = Selector()
    text = phrase
    try:
        changed = True
        while changed:
            changed = False
            for pattern, fn in _SUFFIXES:
                m = pattern.search(text)
                if m:
                    s = fn(s, m)
                    text = text[: m.start()]
                    changed = True
                    break
    except ValueError:
        return None
    words = text.replace(",", " ,").split()
    if not words:
        return None
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
        if nouns and nouns[-1][0] not in ("card", "spell", "perm"):  # ("creature card": card marks the zone)
            joins.add(pending_join or "and")
        nouns.append(c)
        pending_join = ""
        i -= 1
    if pending_join or not nouns:
        return None
    kinds = [c for c in nouns if c[0] not in ("card", "spell", "perm")]
    markers = {c[0] for c in nouns} - {"type", "sub", "player"}
    if any(k[0] == "player" for k in kinds):
        if len(nouns) != 1 or i >= 0:
            return None
        return Selector(player="opponent" if kinds[0][1] == "opponent" else "any")
    types = tuple(dict.fromkeys(v for k, v in kinds if k == "type"))
    subtypes = tuple(dict.fromkeys(v for k, v in kinds if k == "sub"))
    if "or" in joins and "and" in joins:
        return None  # "artifact creature or enchantment": not yet
    if "or" in joins and types and subtypes:
        return None  # "artifact or Goblin": not yet
    if "card" in markers:
        s = replace(s, card=True)
        if s.zones == ("battlefield",):
            s = replace(s, zones=())  # "a creature card": the zone comes from the sentence
    if "spell" in markers:
        s = replace(s, zones=("stack",))
    if "and" in joins and len(types) > 1:
        s = replace(s, types=types, extras=(*s.extras, "all_types"))  # "artifact creature"
    else:
        s = replace(s, types=types)
    s = replace(s, subtypes=subtypes)
    prefix_words = words[: i + 1]
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


# -- evaluation ---------------------------------------------------------------------------
def matches_player(plan: Plan, sel: Selector, pid: str, you: str) -> bool:
    if sel.player is None or pid not in plan.live():
        return False
    if sel.player == "opponent":
        return pid != you
    if sel.player == "you":
        return pid == you
    return True


def matches(plan: Plan, sel: Selector, card: CardInstance, ch: Characteristics, you: str,
            source: str | None = None) -> bool:
    """Does this object match the selector (``you``: the player it's evaluated for)?"""
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
    if zone == "stack" and card.ability is not None:
        return False
    if sel.types:
        if "all_types" in sel.extras:
            if not set(sel.types) <= ch.types:
                return False
        elif not set(sel.types) & ch.types:
            return False
    elif not sel.card and zone == "battlefield" and not ch.types & set(PERMANENT_TYPES):
        return False
    if set(sel.not_types) & ch.types:
        return False
    if sel.subtypes and not set(sel.subtypes) & ch.subtypes:
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
        value = _stat(ch, what)
        if value is None or not {"<=": value <= n, ">=": value >= n, "==": value == n}[op]:
            return False
    for extra in sel.extras:
        if extra == "enchanted" and not _has_attached(plan, card, "Aura"):
            return False
        if extra == "equipped" and not _has_attached(plan, card, "Equipment"):
            return False
        if extra.startswith("counter:") and not card.counters.get(extra[8:], 0):
            return False
    return True


def _stat(ch: Characteristics, what: str) -> int | None:
    if what == "mv":
        return int(ch.mana_value)
    if ch.pt is not None:
        return ch.pt[0] if what == "power" else ch.pt[1]
    raw = ch.power if what == "power" else ch.toughness
    return int(raw) if raw is not None and raw.lstrip("-").isdigit() else None


def _has_attached(plan: Plan, card: CardInstance, subtype: str) -> bool:
    return any(c.attached_to == card.id and subtype in plan.ch(c).subtypes for c in plan.state.cards.values())


def candidates(plan: Plan, sel: Selector, you: str, source: str | None = None) -> list[str]:
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
            if card is None or (zone == "battlefield" and not plan.in_game(card)):
                continue
            if matches(plan, sel, card, plan.ch(card), you, source):
                out.append(cid)
    return out
