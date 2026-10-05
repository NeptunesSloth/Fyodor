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
                  "Lair", "Locus", "Bobblehead", "Cartouche", "Spacecraft"}  # (Lair: the Dragon's Lair lands, "return a non-Lair land you control", wave 1B)
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
_IRREGULAR.update({"oxen": "Ox", "armies": "Army", "spies": "Spy", "cyclopes": "Cyclops"})  # -- static wordings (wave 6E) --
_IRREGULAR.update({"aurochs": "Aurochs"})  # -- trigger tail (wave 15B) -- (its own plural)
_IRREGULAR.update({"heroes": "Hero"})  # -- counters (wave 21D) --
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
    compare: tuple[tuple[str, str, int | str], ...] = ()  # ("mv"|"power"|"toughness", "<="|">="|"==", n) (str: wave 5H)
    # "enchanted", "equipped", "counter:+1/+1", "all_types", "attacking_you", "single_graveyard"
    # (a group constraint: every target from one graveyard — read by language.target_group)
    extras: tuple[str, ...] = field(default_factory=tuple)
    # -- target forms (agent T) --
    # "creature or Vehicle": the types and the subtypes are alternatives (either matches), not both
    union: bool = False
    # an activated or triggered ability on the stack (115.1c-d, 115.2b: "target activated or
    # triggered ability"): "any" | "activated" | "triggered". Mana abilities never use the stack.
    ability: str | None = None
    # -- static grants (wave 15A) -- "artifact, enchantment, or creature with flying": any of these selectors (keys), the qualifier
    # belonging to the last kind only. Only target phrases are read this way (parse_either); other consumers never see it.
    either: tuple[str, ...] = ()

    def key(self) -> str:
        """Canonical and compact: only fields that differ from the defaults."""
        base = asdict(_DEFAULT)
        data = {k: v for k, v in asdict(self).items() if v != base[k]}
        return PREFIX + json.dumps(data, separators=(",", ":"), sort_keys=True)


_DEFAULT = Selector()


def is_plural(phrase: str) -> bool:
    """Does the phrase name a group ("creatures you control", "other Elves")? (its head noun is plural)"""
    for word in phrase.replace(",", " ").split():
        if (_core(word) is not None and _singular(word) != word) or word == "outlaws":  # (outlaws: wave 11F)
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


@_suffix(r"(?:that )?enchanted player controls")
def _enchanted_controls(s: Selector, m: re.Match[str]) -> Selector:
    # -- attached events (wave 16F) -- the player the source (a Curse) enchants, 702.5d
    return replace(s, controller="enchanted")


@_suffix(r"(?:that )?the chosen player controls")
def _chosen_controls(s: Selector, m: re.Match[str]) -> Selector:
    # -- chosen type (wave 16F) -- the player the source chose as it entered (app/rules/chosen.py)
    return replace(s, controller="chosen")


@_suffix(r"(?:from|in) the chosen player's graveyard")
def _chosen_graveyard(s: Selector, m: re.Match[str]) -> Selector:
    return _in_zone(s, "graveyard", "chosen")


# -- static_other sweep (wave 19A) -- also "creatures you control that are equipped" (Hexgold Hoverwings), "that are enchanted"
@_suffix(r"that(?:['’]s| are) (?P<w>enchanted or equipped|enchanted|equipped)")  # -- grammar (wave 11C) -- an Aura or an Equipment on it (303.4, 301.5)
def _enchanted_or_equipped(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, m["w"].replace(" ", "_")))


@_suffix(r"other than ~")
def _other_than_self(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, other=True)


@_suffix(r"that['’]s (?P<w>attacking or blocking|attacking|blocking|tapped|untapped)")
def _thats_status(s: Selector, m: re.Match[str]) -> Selector:
    s2 = _prefix(s, m["w"].replace(" ", "-"))
    assert s2 is not None
    return s2


@_suffix(r"other than that (?:creature|permanent)")  # -- stack interaction (wave 23B) -- Pawpatch Recruit: not the object the trigger's event is about
def _other_than_event(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "not_event"))


@_suffix(r"that attacked this turn")  # -- combat (wave 5C) -- declared as attackers this turn (508.1; 508.4: not put)
def _attacked_this_turn(s: Selector, m: re.Match[str]) -> Selector:
    if not m.string[: m.start()].endswith("creatures"):
        raise ValueError("only \"creatures that attacked this turn\" (a group on the battlefield)")
    return replace(s, extras=(*s.extras, "attacked_this_turn"))


@_suffix(r"drawn this turn")  # -- drawn this turn (wave 18G) -- "cards in your hand drawn this turn" (Sylvan Library): TurnLog.drawn
def _drawn_this_turn(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "drawn_this_turn"))


# -- both colors (wave 6D) -- "a spell that's both red and white" (the Mimics): each of the colors (105.2)
@_suffix(r"that['’]s both (?P<c1>" + "|".join(COLORS) + r") and (?P<c2>" + "|".join(COLORS) + r")")
def _thats_both(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "all_colors:" + COLORS[m["c1"]] + COLORS[m["c2"]]))


DEFENDED = "defended_player"  # -- triggers (wave 19B) -- a non-targeted "defending player controls": the attack event's player (bound as it's put on the stack)
THAT_PLAYER = "that_player"  # -- damage wordings (wave 6B) -- a controller the trigger event's player binds


# -- damage history (wave 6B) -- "creature that was dealt damage this turn", "each creature dealt damage this turn",
# "creature that dealt damage [to you] this turn" (app/rules/damage_history.py)
@_suffix(r"that dealt damage (?P<you>to you )?this turn")
def _dealt_damage_this_turn(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "dealt_damage_you" if m["you"] else "dealt_damage"))


# -- crew & saddle (wave 23D) -- "creature that crewed it this turn" / "that saddled it this turn": tapped this turn to pay a crew / saddle
# ability of the source (702.122c, 702.171c; app/rules/crew_saddle.py)
@_suffix(r"that (?P<k>crewed|saddled) (?:it|~|this (?:Vehicle|Mount|permanent)) this turn")
def _crewed_it(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "crewed_it" if m["k"] == "crewed" else "saddled_it"))


@_suffix(r"dealt damage by (?:this creature|~) this turn")  # -- damage history (wave 19E) -- "a creature dealt damage by ~ this turn"
def _dealt_damage_by_source(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "dealt_damage_by_source"))


@_suffix(r"(?:that (?:was|were) )?dealt damage this turn")
def _was_dealt_damage_this_turn(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "was_dealt_damage"))


@_suffix(r"that player controls")  # "destroy target artifact that player controls" in a trigger about a player: bound
def _that_player_controls(s: Selector, m: re.Match[str]) -> Selector:  # to it as the trigger is put on the stack
    return replace(s, controller=THAT_PLAYER)  # (triggers.bind_that_player: "player:<id>"; unbound, nothing matches)


@_suffix(r"(?P<b>blocking (?:it|this creature|~)|(?:it['’]s|this creature is|~ is) blocking)")  # "target creature blocking it" / "… it's blocking": the source's
def _blocking_source(s: Selector, m: re.Match[str]) -> Selector:  # blocks (509.1; scripts._event_refs_ok: "it" is ~)
    return replace(s, extras=(*s.extras, "blocking_source" if m["b"].startswith("blocking") else "blocked_by_source"))


@_suffix(r"that has an Adventure")  # -- trigger other (wave 25B) -- 715.1: the card is an adventurer card ("It doesn't need to have gone on the adventure first")
def _has_adventure(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "has_adventure"))


@_suffix(r"with \{[xX]\} in (?:its|their) mana costs?")  # -- activated wordings (wave 15D) -- "a spell with {X} in its mana cost" (107.3)
def _has_x_cost(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "x_cost"))


@_suffix(r"with toughness greater than (?:its|their) power")  # (Ghalta the Immovable, Bedrock Tortoise)
def _toughness_over_power(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "toughness_gt_power"))
# -- end damage history (wave 6B) --


@_suffix(r"(?:that(?:['’]s| are) )?attacking you")  # (wave 17D: also plural / bare)
def _attacking_you(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, attacking=True, extras=(*s.extras, "attacking_you"))


@_suffix(r"that(?:['’]s| is| are) (?P<list>(?:" + "|".join(COLORS) + r")(?:, (?:" + "|".join(COLORS) + r"))*(?:,? or (?:" + "|".join(COLORS) + r"))?)")
def _thats_colored(s: Selector, m: re.Match[str]) -> Selector:  # (wave 19D: "that's white, blue, black, or red")
    found = tuple(COLORS[c] for c in re.findall("|".join(COLORS), m["list"]))
    return replace(s, colors=(*s.colors, *found))


# -- token & pump wordings (wave 6C) -- "each other creature you control that's a Fungus or Saproling", "each creature that's
# a Barbarian, a Warrior, or a Berserker": any of these creature types (205.3m)
@_suffix(r"that['’]s (?P<list>an? [A-Z][\w'’-]*(?:(?:,|,? or|,? and/or) (?:an? )?[A-Z][\w'’-]*)*)")
def _thats_types(s: Selector, m: re.Match[str]) -> Selector:
    words = [w for w in re.split(r",? (?:or|and/or) |, ", m["list"]) if w]
    subs = [_core(re.sub(r"^an? ", "", w)) for w in words]
    if not subs or any(c is None or c[0] != "sub" for c in subs):
        raise ValueError("not a list of creature types")
    return replace(s, extras=(*s.extras, "subtype_any:" + "|".join(c[1] for c in subs if c is not None)))


@_suffix(r"that(?:['’]s| is| are) one or more colors")  # (wave 15A: "permanents they control that are one or more colors")
def _thats_colors(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, colorless=False)


# -- static grants & selectors (wave 15A) -- "creatures that aren't enchanted", "nonland permanents that aren't legendary / that's
# not historic" (a negated quality: 700.6 historic, 303.4 / 301.5 enchanted / equipped, 205.4 supertypes, 105 colors)
_NOT_EXTRAS = ("not_enchanted", "not_equipped", "not_historic")


@_suffix(r"that(?:['’]s not| isn['’]t| aren['’]t| is not| are not) (?P<w>enchanted|equipped|historic|legendary|snow|basic|" + "|".join(COLORS) + ")")
def _thats_not(s: Selector, m: re.Match[str]) -> Selector:
    w = m["w"]
    if w in COLORS:
        return replace(s, not_colors=(*s.not_colors, COLORS[w]))
    if w in SUPERTYPES:
        return replace(s, not_supertypes=(*s.not_supertypes, SUPERTYPES[w]))
    return replace(s, extras=(*s.extras, "not_" + w))


@_suffix(r"you own")
def _you_own(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, owner="you")


@_suffix(r"(?:an opponent owns|you don't own|(?:is |are )?owned by (?:another player|an opponent))")  # (wave 25B: owned by another player)
def _opp_own(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, owner="opponent")


@_suffix(r"you control but don't own")  # -- trigger other (wave 25B) -- 108.3 / 110.2: you control it, another player owns it (Edea)
def _control_not_own(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, controller="you", owner="opponent")


@_suffix(r"(?:from|in) your (?P<z>graveyard|hand|library)")
def _your_zone(s: Selector, m: re.Match[str]) -> Selector:
    return _in_zone(s, m["z"], "you")


@_suffix(r"(?:from|in) (?:a|any) graveyard")
def _any_graveyard(s: Selector, m: re.Match[str]) -> Selector:
    return _in_zone(s, "graveyard", None)


@_suffix(r"(?:from|in) that player's graveyard")  # -- if you do (wave 15C) -- the player a trigger is about (bound like
def _that_players_graveyard(s: Selector, m: re.Match[str]) -> Selector:  # "that player controls": triggers.bind_that_player)
    return _in_zone(s, "graveyard", "that_player")


@_suffix(r"(?:from|in) (?:an opponent's|your opponents') graveyards?")
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
    if n is None and m.group(2).lower() == "x" and m["dir"] == "less":
        n = X_VALUE  # -- control (wave 3K) -- "target creature with mana value X or less" (Dominate): the X of the spell (wave 19F: or power X)
    if n is None:
        raise ValueError("X comparisons need a value")
    what = {"mana value": "mv", "power": "power", "toughness": "toughness"}[m["what"]]
    return replace(s, compare=(*s.compare, (what, "<=" if m["dir"] == "less" else ">=", n)))


@_suffix(r"with power or toughness (?P<n>\d+) or (?P<dir>less|greater)")  # (wave 15A: Tetsuko Umezawa — either one)
def _power_or_toughness(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, f"pot:{'<=' if m['dir'] == 'less' else '>='}{m['n']}"))


@_suffix(r"with a basic land type")  # -- tutor (wave 20D) -- 205.3i: "a land card with a basic land type" (Nervous Gardener, Perilous Forays)
def _basic_land_type(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "basic_land_type"))


@_suffix(r"with total power and toughness (?P<n>\d+) or (?P<dir>less|greater)")  # -- put from hand (wave 19E) -- Meek Attack
def _total_pt(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, f"pts:{'<=' if m['dir'] == 'less' else '>='}{m['n']}"))


@_suffix(r"with (?P<what>mana value|power|toughness) (?P<dir>greater|less) than " + _NUM)  # (wave 15A: strictly, 107.1)
def _compare_strict(s: Selector, m: re.Match[str]) -> Selector:
    n = _n(m.group(3))
    if n is None or m.group(3) == "x":
        raise ValueError("X comparisons need a value")
    what = {"mana value": "mv", "power": "power", "toughness": "toughness"}[m["what"]]
    return replace(s, compare=(*s.compare, (what, ">" if m["dir"] == "greater" else "<", n)))


@_suffix(r"with (?P<what>mana value|power|toughness) " + _NUM.replace("|x)", "|[xX])"))
def _equal(s: Selector, m: re.Match[str]) -> Selector:
    n = _n(m.group(2))
    if n is None and m.group(2).lower() == "x":
        n = X_VALUE  # -- reanimation (wave 10A) -- "target creature card with mana value X" (Postmortem Lunge): the spell's X (wave 19F: or power)
    if n is None:
        raise ValueError("X comparisons need a value")
    what = {"mana value": "mv", "power": "power", "toughness": "toughness"}[m["what"]]
    return replace(s, compare=(*s.compare, (what, "==", n)))


# -- reanimation (wave 10A) -- "target creature card with mana value less than or equal to ~'s power from your graveyard"
# (Carmen, Cruel Skymarcher; Fiendish Panda), "… with power less than ~'s" (Mirko): a comparison with a characteristic of
# the ability's source, as it is or (once it has left the battlefield: "When this creature dies") as it last existed
# (608.2h). Only a card in a graveyard is read this way (_parse refuses the others: a spell or permanent selector has no
# such users), and a source with no such value (no power: not a creature) matches nothing.
SOURCE_STAT = "src:"
EVENT_STAT = "evt:"
_REF_OPS = {"less than or equal to": "<=", "less than": "<", "equal to": "==", "greater than or equal to": ">=",
            "greater than": ">"}
_REF_STAT = {"mana value": "mv", "power": "power", "toughness": "toughness"}


@_suffix(r"with (?P<what>mana value|power|toughness) (?P<op>less than or equal to|less than|equal to|greater than or equal to|"
         r"greater than) (?:~|this creature)'s(?: (?P<ref>mana value|power|toughness))?")
def _compare_source(s: Selector, m: re.Match[str]) -> Selector:
    if m["ref"] is None and m["what"] == "mana value":
        raise ValueError("incomplete reference")  # ("mana value less than ~'s": which characteristic?)
    ref = m["ref"] or m["what"]  # ("power less than Mirko's": the same characteristic)
    return replace(s, compare=(*s.compare, (_REF_STAT[m["what"]], _REF_OPS[m["op"]], SOURCE_STAT + _REF_STAT[ref])))


@_suffix(r"with (?P<eq>equal or )?lesser (?P<what>mana value|power|toughness)(?: than the creature that died)?")
def _compare_event(s: Selector, m: re.Match[str]) -> Selector:
    # -- reanimation (wave 16F) -- "return target creature card with lesser mana value from your graveyard" (Jackdaw Savior,
    # Riveteers Ascendancy): less than the object the trigger is about (the creature that died / was sacrificed), as it last
    # existed (608.2h); triggers.bind_event_stat swaps in the number as the ability goes on the stack (an unbound one matches nothing)
    return replace(s, compare=(*s.compare, (_REF_STAT[m["what"]], "<=" if m["eq"] else "<", EVENT_STAT + _REF_STAT[m["what"]])))


# -- static_other sweep (wave 17C) -- "Exile each creature and planeswalker with mana value less than the revealed card's mana value."
# (Calamity of the Titans): a comparison with the card the source spell's additional cost revealed (its payment record)
REVEALED_STAT = "rev:"


@_suffix(r"with (?P<what>mana value|power|toughness) (?P<op>less than or equal to|less than|equal to|greater than or equal to|"
         r"greater than) the revealed card's (?P<ref>mana value|power|toughness)")
def _compare_revealed(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, compare=(*s.compare, (_REF_STAT[m["what"]], _REF_OPS[m["op"]], REVEALED_STAT + _REF_STAT[m["ref"]])))


def revealed_stat(plan: Plan, source: str | None, what: str) -> int | None:
    """The mana value / power / toughness of the card the source spell's cost revealed (one card, from its payment record)."""
    record = plan.rules.payments.get(plan.rules.object_id(source)) if source else None
    ids = record.revealed if record is not None else []
    card = plan.state.cards.get(ids[0]) if len(ids) == 1 else None
    return _stat(plan.ch(card), what) if card is not None else None


def source_stat(plan: Plan, source: str | None, what: str) -> int | None:
    """The source's mana value / power / toughness: on the battlefield as it is, else as it last existed there."""
    card = plan.state.cards.get(source or "")
    if card is None:
        return None
    if card.zone.endswith(":battlefield"):
        return _stat(plan.ch(card), what)
    snaps = [x for x in plan.rules.lki.values() if x.card == card.id and x.zone.endswith(":battlefield")]
    if not snaps:
        return None
    from app.rules.triggers import _lki_characteristics

    return _stat(_lki_characteristics(plan, max(snaps, key=lambda x: int(x.object_id.rsplit(".", 1)[-1]))), what)
# -- end reanimation (wave 10A) --


# -- token & pump wordings (wave 6C) -- keywords a selector may ask about but a grant doesn't give ("if you control no
# creatures with decayed": read from the object's keywords, like the others)
_WITH_KEYWORDS = (*KEYWORDS, "decayed", "infect", "wither", "fear", "shadow", "horsemanship", "intimidate", "skulk", "convoke",
                  "modular", "toxic", "mutate", "awaken", "cascade")  # (wave 21D: "a spell with cascade")  # (wave 20C: toxic/mutate/awaken; wave 19D: "each creature you control with modular": a printed keyword line; level up is rewritten into
# an activated ability and statics by app/rules/levelers.py, so it is no keyword of the object and stays unread)


@_suffix(r"(?:with|that has) (?P<kw>" + "|".join(_WITH_KEYWORDS) + r")")  # (wave 15B: "a spell that has convoke")
def _with_kw(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, with_keywords=(*s.with_keywords, m["kw"]))


@_suffix(r"with (?:cycling|cycling abilities)")  # -- reanimation (wave 20C) -- 702.29f: typecycling abilities are cycling abilities
def _with_cycling(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "cycling_ability"))


@_suffix(r"with (?:an? morph ability|morph abilities)")  # -- hidden exile (wave 18A) -- 702.37b: megamorph is a morph ability too
def _with_morph(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "morph_ability"))


@_suffix(r"without (?P<kw>" + "|".join(_WITH_KEYWORDS) + r")")
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
SOURCE_COUNTERS = "counters:"  # a comparison with the number of a kind of counters on the source (as it last existed)
# -- control change (wave 20E) -- "target creature with power less than or equal to the number of creatures you control" (Beguiler of
# Wills), "… with mana value less than or equal to the number of Vampires you control" (Dominating Vampire): a comparison with the
# number of permanents the ability's controller controls that fit a selector, counted when the target is chosen and again as it resolves
COUNT_STAT = "cnt:"
_COUNT_CMP = re.compile(r"(?:,)? with (?P<what>mana value|power|toughness) (?P<op>less than or equal to|less than) the number of "
                        r"(?P<k>[A-Za-z' -]+? you control)$")


def _compare_count(s: Selector, m: re.Match[str]) -> Selector:
    counted = parse(m["k"])
    if counted is None or counted.player is not None or counted.card or counted.zones != ("battlefield",) or counted.controller != "you" \
            or counted.compare or counted.extras:
        raise ValueError("a count this comparison doesn't read")
    return replace(s, compare=(*s.compare, ({"mana value": "mv", "power": "power", "toughness": "toughness"}[m["what"]],
                                            "<=" if m["op"] == "less than or equal to" else "<", COUNT_STAT + counted.key())))


_SUFFIXES.insert(0, (_COUNT_CMP, _compare_count))  # (first: "… you control" is also the controller suffix)


# "each nonland permanent with mana value equal to the number of charge counters on ~" (Ratchet Bomb, Blast Zone),
# "a spell with mana value equal to the number of charge counters on ~" (Chalice of the Void): the source's counters as
# it is, or as it last existed on the battlefield (sacrificed as a cost: 608.2h, 122.2)
@_suffix(r"with (?P<what>mana value|power) (?P<op>equal to|less than or equal to) the number of (?P<k>\+1/\+1|[a-z]+) counters on "  # (wave 20E: power)
         r"(?:~|this (?:artifact|land|creature|enchantment|permanent))")
def _mv_source_counters(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, compare=(*s.compare, ("mv" if m["what"] == "mana value" else "power", "==" if m["op"] == "equal to" else "<=",
                                            SOURCE_COUNTERS + m["k"])))


COLORS_SPENT = "colors_spent"  # -- trigger other (wave 25B) -- converge: the colors of mana spent to cast the source (its payment record)


@_suffix(r"with (?P<what>mana value|power) (?P<op>equal to|less than or equal to) the number of colors of mana spent to cast "
         r"(?:~|this (?:spell|creature|permanent|artifact|enchantment))")
def _mv_colors_spent(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, compare=(*s.compare, ("mv" if m["what"] == "mana value" else "power", "==" if m["op"] == "equal to" else "<=", COLORS_SPENT)))


def _source_counters(plan: Plan, source: str | None, kind: str) -> int | None:
    src = plan.state.cards.get(source or "")
    if src is None:
        return None
    if src.zone.endswith(":battlefield"):
        return src.counters.get(kind, 0)
    snaps = [s for s in plan.rules.lki.values() if s.card == src.id and s.zone.endswith(":battlefield")]
    if not snaps:
        return None
    last = max(snaps, key=lambda s: int(s.object_id.rsplit(".", 1)[-1]))
    return last.counters.get(kind, 0)


# -- amounts (wave 12C) -- "cards named ~ in all graveyards" (Kindle): the source's name (201.2), read with the source in play
@_suffix(r"named ~")
def _named_self(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "named_self"))


# -- history (wave 22E) -- "a creature spell that shares a creature type with your commander" (Path of Ancestry): one of the creature types
# of one of the matcher's commanders (903.3: the cards its owner's deck names, wherever they are), read as the cards are
@_suffix(r"that shares a creature type with your commander")
def _shares_commander_type(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "shares_commander_type"))


def _shares_commander_type_now(plan: Plan, ch: Characteristics, you: str) -> bool:
    from app.rules.creature_types import CREATURE_TYPES

    mine = ch.subtypes & CREATURE_TYPES
    return any(mine & (plan.ch(c).subtypes & CREATURE_TYPES) for c in plan.state.cards.values()
               if c.commander_key is not None and c.owner == you)


# "each creature that entered this turn", "target non-Human creature that entered this turn", "each creature that
# entered the battlefield under your control this turn": the permanent is an object that entered this turn (400.7: a
# new object if it left and came back), read from this turn's log (app/rules/history.py)
@_suffix(r"that entered (?:the battlefield )?(?P<you>under your control )?this turn")
def _entered_this_turn(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "entered_this_turn_you" if m["you"] else "entered_this_turn"))


def _entered_now(plan: Plan, card: CardInstance, you: str | None) -> bool:
    from app.rules.history import log_for

    if not card.zone.endswith(":battlefield"):
        return False
    oid = plan.oid(card)
    return any(e.object_id == oid and (you is None or e.controller == you) for e in log_for(plan, False).entered)


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
                 "not_chosen_color": "color", "chosen_name": "card name"}  # (-- card names (wave 22B) -- app/rules/card_names.py)


@_suffix(r"(?:with|that has) (?:the chosen|that) name")  # -- card names (wave 22B) -- 709.4a: one of its names is the chosen name
def _of_chosen_name(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "chosen_name"))


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
    if what == "card name":  # -- card names (wave 22B) -- the answer given earlier in the same resolution
        return replace(sel, extras=(*rest, "name:" + value))
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
    label = {"creature type": "Chosen creature type", "color": "Chosen color", "card name": "Chosen card name"}[what]
    value = card.choices.get(label)
    return value.strip() if value else None


def _chosen_ok(plan: Plan, sel: Selector, ch: Characteristics, source: str | None) -> bool:
    what = chosen_what(sel)
    if what == "card name":  # -- card names (wave 22B) -- the source permanent's recorded name
        from app.rules import card_names

        return card_names.matches(plan, source, ch)
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
    if low.endswith("us"):  # -- token & pump wordings (wave 6C) -- "Fungus", "Octopus" (singular nouns)
        return word
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
    if low == "unblocked":  # -- keywords (wave 15E) -- ninjutsu 702.49a: "unblocked attacking creature" (509.1h: not blocked)
        return replace(s, attacking=True, extras=(*s.extras, "unblocked"))
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
    if low in ("enchanted", "equipped", "modified", "historic", "goaded"):  # (wave 11C: modified 700.9, historic 700.6; wave 22E: goaded 701.15)
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


# -- copy abilities (wave 19E) -- "target activated or triggered ability you control from an enchantment source" / "… from another
# legendary source that's not a commander" (Weaver of Harmony, Peregrine Dynamo): the ability's source as it last existed
# (608.2h; ``source_matches``), encoded as the extras "src:<selector key>" and "src_nc".
_FROM_SOURCE = re.compile(r" from (?P<o>another )?(?:an? )?(?P<w>[a-z]+(?: [a-z]+)*?) source(?P<nc> that's not a commander)?$")
# -- stack interaction (wave 23B) -- "from an artifact, creature, enchantment, or land" (Interdict): the source is any of those kinds
_FROM_KINDS = re.compile(r" from an? (?P<w>(?:(?:artifact|creature|enchantment|land|planeswalker), )+or (?:artifact|creature|enchantment|land|planeswalker))$")


def _source_selector(w: str, other: str | None) -> Selector | None:
    """One kind of source, or "an artifact or enchantment" / "an artifact, creature, or land": any of them (the selector's ``either``)."""
    parts = re.split(r",? or |, ", w)
    subs = [next((x for q in (p, p + " permanent") if (x := parse(("another " if other else "") + q)) is not None
                 and x.zones == ("battlefield",) and x.player is None and not x.extras and x.ability is None and not x.card), None)
            for p in parts]
    if any(x is None for x in subs):
        return None
    return subs[0] if len(subs) == 1 else Selector(either=tuple(x.key() for x in subs if x is not None))


def _from_source_suffix(s: Selector, m: re.Match[str]) -> Selector:
    sub = _source_selector(m["w"], m.groupdict().get("o"))
    if sub is None:
        raise ValueError("unread source condition")
    return replace(s, extras=(*s.extras, f"src:{sub.key()}", *(("src_nc",) if m.groupdict().get("nc") else ())))


_SUFFIXES.insert(0, (_FROM_SOURCE, _from_source_suffix))
_SUFFIXES.insert(0, (_FROM_KINDS, _from_source_suffix))


def source_matches(plan: Plan, card: CardInstance, extra: str, you: str, source: str | None) -> bool:
    """Is the source of this ability on the stack what the "src:" / "src_nc" extra names (as it last existed)?"""
    from app.rules import triggers  # (triggers imports this module)

    entry = plan.rules.stack.get(card.id) if plan.rules is not None else None
    then = triggers._object_then(plan, entry.source_card, entry.source_object) if entry is not None else None
    if then is None:
        return False
    if extra == "src_nc":
        return then[0].commander_key is None
    return matches(plan, from_key(extra[4:]), then[0], then[1], you, source)


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


# -- counters (wave 21D) -- "Pest, Bat, Insect, Snake, and Spider you control" (Blech): a list of creature types joined by "and" names an
# object with any of them, like "Pest, Bat, or Spider you control" (the same group)
_TYPE_AND = re.compile(r"^(?P<pre>(?:other |another )?)(?P<list>[A-Z][A-Za-z'\-]+(?:, [A-Z][A-Za-z'\-]+)*,? and [A-Z][A-Za-z'\-]+)"
                       r"(?P<post>(?: you control)?)$")


def _type_and(phrase: str) -> str:
    from app.rules.creature_types import CREATURE_TYPES

    m = _TYPE_AND.match(phrase)
    if m is None:
        return phrase
    words = re.split(r",? and |, ", m["list"])
    if not all(w in CREATURE_TYPES or _IRREGULAR.get(w.lower()) in CREATURE_TYPES or w[:-1] in CREATURE_TYPES for w in words):
        return phrase
    return f"{m['pre']}{', '.join(words[:-1])}{',' if len(words) > 2 else ''} or {words[-1]}{m['post']}"


def parse(phrase: str) -> Selector | None:
    """A noun phrase without its determiner ("nonland permanent an opponent controls") → Selector."""
    return _parse(_type_and(phrase.strip()))


# -- outlaws (wave 11F) -- 700.12: an object with the Assassin, Mercenary, Pirate, Rogue and/or Warlock creature types
_OUTLAW = re.compile(r"(?P<pre>(?:another |other )?)outlaw(?P<pl>s?)(?P<post>(?: .*)?)")
OUTLAW_TYPES = "Assassin|Mercenary|Pirate|Rogue|Warlock"


def _outlaws(phrase: str) -> Selector | None:
    """"another outlaw", "outlaws you control", "outlaw spell": any permanent (or spell) with one of those types (700.12a)."""
    m = _OUTLAW.fullmatch(phrase)
    if m is None:
        return None
    noun = re.match(r"\s*(?:spells?|cards?|creatures?|permanents?|tokens?)\b", m["post"]) is not None  # "outlaw spell", "outlaw cards"
    base = _parse((m["pre"] + ("" if noun else "permanent" + m["pl"]) + m["post"]).strip())
    return replace(base, extras=(*base.extras, "subtype_any:" + OUTLAW_TYPES)) if base is not None else None


_EITHER = re.compile(r"^(?P<head>[a-z]+(?:, [a-z]+)*),? or (?P<last>[a-z]+ (?:with|without) .+)$"
                     # -- target forms (wave 19E) -- "noncreature artifact or noncreature enchantment": each kind has its own qualifier
                     r"|^(?P<head2>non[a-z]+ [a-z]+) or (?P<last2>non[a-z]+ [a-z]+)$")


def parse_either(phrase: str) -> Selector | None:
    """"artifact, enchantment, or creature with flying" (a target phrase: 115.1): an artifact, an enchantment, or a creature with
    flying — the qualifier is the last kind's only."""
    m = _EITHER.match(phrase.strip())
    if m is None:
        return None
    a, b = _parse(m["head"] or m["head2"]), _parse(m["last"] or m["last2"])
    if a is None or b is None or a.player or b.player or a.zones != ("battlefield",) or b.zones != ("battlefield",):
        return None
    return Selector(either=(a.key(), b.key()))


# -- stack interaction (wave 23B) -- "activated ability, triggered ability, or legendary spell" (Tale's End), "triggered ability or
# colorless spell" (Consign to Memory), "activated ability, triggered ability, or noncreature spell" (Louisoix's Sacrifice): one
# object on the stack that is any of these (115.1: each kind its own selector; a spell is never an ability, 115.2b)
_ABILITY_OR_SPELL = re.compile(r"^(?P<abil>activated ability, triggered ability|activated or triggered ability|activated ability|triggered ability)"
                               r",? or (?P<spell>(?:[a-z]+ )+spell)$")


def parse_stack_union(phrase: str) -> Selector | None:
    m = _ABILITY_OR_SPELL.match(phrase.strip())
    if m is None:
        return None
    spell = _parse(m["spell"])
    if spell is None or spell.zones != ("stack",) or spell.ability is not None or spell.either or spell.player is not None:
        return None
    kinds = ("activated", "triggered") if "," in m["abil"] else ("any",) if " or " in m["abil"] else (m["abil"].split()[0],)
    return Selector(either=(*(replace(_DEFAULT, zones=("stack",), ability=k).key() for k in kinds), spell.key()), zones=("stack",))


_SPELL_OR = re.compile(r"^spell or (?P<perm>.+)$")


def parse_spell_or(phrase: str) -> Selector | None:
    """-- static_other sweep (wave 17C) -- "spell or nonland permanent an opponent controls" / "spell or creature" / "spell or permanent
    that's red or green" (a target phrase: a spell on the stack, or a permanent): the qualifiers (who controls it, a color, a mana
    value) are both kinds'; "nonland", a card type or a subtype is the permanent's own (a spell is never a land, and "creature" is no
    limit on spells here)."""
    m = _SPELL_OR.match(phrase.strip())
    if m is None:
        return None
    perm = _parse(m["perm"])
    if perm is None or perm.player or perm.card or perm.zones != ("battlefield",) or perm.either or perm.ability or perm.union or perm.extras:
        return None
    spell = replace(perm, zones=("stack",), types=(), not_types=(), subtypes=(), not_subtypes=(), supertypes=(), not_supertypes=(),
                    token=None, tapped=None, attacking=False, blocking=False, in_combat=False)
    if spell.controller == "you" and perm.controller != "you":
        return None
    return Selector(either=(spell.key(), perm.key()), zones=("stack", "battlefield"))


# -- granted from object (wave 18F) -- 607.1a / 613.1f: a quoted grant that names its granter ("Sacrifice Blazing Torch"): the
# granting object, as it is now (layers.py binds ‹granter› to its object id; none yet while the grant is only being read)
GRANTER = r"‹granter(?:#(?P<oid>[^›]+))?›"


@lru_cache(maxsize=8192)
def _parse(phrase: str) -> Selector | None:
    if (g := re.fullmatch(GRANTER, phrase)) is not None:
        return Selector(extras=("oid:" + (g["oid"] or ""),))
    if "outlaw" in phrase:
        return _outlaws(phrase)
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
    if any(isinstance(c[2], str) and c[2].startswith((SOURCE_STAT, EVENT_STAT)) for c in s.compare) and (
            (s.zones != ("graveyard",) or not s.card) and (s.zones != ("battlefield",) or s.card)):
        return None  # -- reanimation (wave 10A) -- (only cards in a graveyard are compared with the source; -- keywords
        # (wave 15E) -- or permanents: mentor's "target attacking creature with power less than this creature's power")
    if any(c[1] == "==" and c[2] == X_VALUE for c in s.compare) and not ((s.zones == ("graveyard",) and s.card) or (s.zones == ("battlefield",) and not s.card
                                                                                  and not re.search(r"\bspells?\b", text)) or re.search(r"\bspells?\b", text)):
        return None  # -- reanimation (wave 10A) -- ("mana value X" exactly: read for a card in a graveyard, or -- wave 17B -- a permanent;
        # not a spell: the X in its cost counts on the stack (202.3e), which the selector's mana value doesn't read — wave 19F: it does,
        # "counter target spell with mana value X" compares the value with X on the stack)
    # (wave 16C: "artifact, creature, or enchantment an opponent controls with mana value 3 or greater": a qualifier after the
    # controller clause is the whole phrase's)
    if qualified and re.search(r", or \S+$", text) and not re.search(
            r", or \w+ (?:an opponent controls|you control|your opponents control|you don't control|that player controls) with", phrase):
        # "artifact, enchantment, or creature with flying": the qualifier is the last item's
        # only (any artifact; a creature with flying), which a selector can't say: not a guess
        return None
    # -- recursion & tutors (wave 4M) -- "Angel or Human creature card" (Bruna, the Fading Light): subtypes any of which
    # matches, narrowing one card type (205.3); "historic card" (700.6: legendary, artifact or Saga)
    if text.strip() in ("historic card", "historic cards") and not qualified:
        return replace(s, card=True, zones=() if s.zones == ("battlefield",) else s.zones, extras=(*s.extras, "historic"))
    # -- historic (wave 6D) -- "a historic spell" (Jhoira), "another nontoken historic permanent" (700.6)
    hist = re.fullmatch(r"(?P<pre>(?:nontoken )?)historic (?P<rest>spells?|permanents?)", text.strip())
    if hist is not None and not qualified:
        base = _parse(hist["pre"] + hist["rest"])
        if base is None or base.types or base.subtypes or base.card:
            return None
        return replace(s, zones=base.zones, token=base.token, extras=(*s.extras, "historic"))
    alt_subs = re.fullmatch(r"(?P<subs>[A-Z][\w'’-]*(?:,? or [A-Z][\w'’-]*)+) (?P<rest>(?:creature|artifact|enchantment|land|planeswalker)s?(?: cards?| spells?)?)",
                            text.strip())  # (wave 15B: also "Beast or Bird creature", "Beast or Bird creature spell")
    if alt_subs is not None:
        subs = [_core(w) for w in re.split(r",? or ", alt_subs["subs"])]
        base = _parse(alt_subs["rest"]) if all(c is not None and c[0] == "sub" for c in subs) else None
        if base is None or base.subtypes or base.union or len(base.types) != 1 or base.player is not None:
            return None
        return replace(s, card=base.card, zones=base.zones if s.zones == ("battlefield",) else s.zones, types=base.types,
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
    sub_and = False  # (wave 19F) a list of kinds with a subtype in it: "Mounts and Vehicles"
    while i >= 0:
        w = words[i]
        if w in (",", "or", "and/or"):
            pending_join = "or"
            i -= 1
            continue
        if w == "and" and nouns and nouns[-1][0] in ("type", "sub") and i > 0 and (left := _core(words[i - 1])) is not None \
                and left[0] in ("type", "sub"):  # (wave 19F: also subtypes — "the number of Mounts and Vehicles you control")
            pending_join = "or"  # -- static_other sweep (wave 17C) -- "each creature and planeswalker", "creatures and planeswalkers": either type
            sub_and = sub_and or "sub" in (nouns[-1][0], left[0])
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
        if s.card:
            return None  # (a commander card in the command zone: not yet; -- static_other sweep (wave 17C) -- a commander spell is one)
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
    if sub_and and any(w.lower() not in (",", "another", "other") for w in prefix_words):
        return None  # (a qualifier — "equipped", "tapped", "nonartifact" — belongs to which of the kinds? not read)
    for k, w in enumerate(reversed(prefix_words)):
        if w in (",",):
            continue
        if w in ("or", "and"):  # "black or red", "white and/or blue": colors are alternatives
            j = len(prefix_words) - 1 - k
            before = j - 1
            while before > 0 and prefix_words[before] == ",":  # (wave 19D: "white, blue, black, or red": a list, 105.1)
                before -= 1
            if 0 < j < len(prefix_words) - 1 and prefix_words[before].lower() in COLORS \
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
    if kind not in ("attack", "targeted"):  # (wave 23B: the object that became a target, for "other than that creature")
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
    if zone == "exile" and card.face_down:  # -- review (wave 21) -- 406.3a: a card exiled face down has no characteristics (Crackling
        # Drake's "instant and sorcery cards you own in exile" never counts it, nor tells anyone what it is)
        from app.rules.characteristics import Characteristics

        ch = Characteristics(name="")
    if sel.either:  # (wave 15A) any one of the alternatives (each reads its own zone: wave 17C; a spell on the stack: wave 17D)
        return (zone in sel.zones or zone == "stack") and any(matches(plan, from_key(k), card, ch, you, source, attacker) for k in sel.either)
    if sel.zones and zone not in sel.zones:
        return False
    if not sel.zones and zone in ("battlefield", "stack"):
        return False  # "a creature card" isn't a permanent or a spell
    if sel.zone_owner == "you" and card.owner != you:
        return False
    if sel.zone_owner == "opponent" and card.owner == you:
        return False
    if (sel.zone_owner == "that_player" or (sel.zone_owner or "").startswith("player:")) \
            and card.owner != (sel.zone_owner or "")[7:]:
        return False  # (wave 15C) unbound "that_player": nothing matches
    any_stack = sel.ability == SPELL_OR_ABILITY  # -- stack interaction (wave 5B) --
    if zone == "stack" and not any_stack and (card.ability is not None) != (sel.ability is not None):
        return False  # a spell isn't an ability, and an ability isn't a spell (115.2b)
    if sel.ability is not None and not any_stack and not _ability_kind(plan, card, sel.ability):
        return False
    if any_stack and card.ability is not None and not _ability_kind(plan, card, "any"):
        return False
    if "single_target" in sel.extras and (zone != "stack" or not single_target(plan, card)):  # (wave 5B)
        return False
    if any(x.startswith("src") and (zone != "stack" or card.ability is None or not source_matches(plan, card, x, you, source))
           for x in sel.extras):  # -- copy abilities (wave 19E) -- "… from an enchantment source"
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
    if sel.controller is not None and (sel.controller in (THAT_PLAYER, DEFENDED) or (  # -- damage wordings (wave 6B) --
            sel.controller.startswith("player:") and card.controller != sel.controller[7:])):
        return False
    if sel.controller == "defending" and card.controller not in defending_players(plan, source, attacker):
        return False
    if sel.controller == "chosen" or sel.zone_owner == "chosen":
        from app.rules import chosen

        who = chosen.player_of(plan, source) if source is not None else None
        if who is None or (card.controller != who if sel.controller == "chosen" else card.owner != who):
            return False
    if sel.controller == "enchanted":
        src = plan.state.cards.get(source or "")
        if src is None or src.attached_player is None or card.controller != src.attached_player:
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
        if isinstance(n, str) and n.startswith(REVEALED_STAT):  # -- static_other sweep (wave 17C) --
            revealed = revealed_stat(plan, source, n[len(REVEALED_STAT):])
            if revealed is None:
                return False
            n = revealed
        elif isinstance(n, str) and n.startswith(SOURCE_STAT):  # -- reanimation (wave 10A) --
            ref_value = source_stat(plan, source, n[len(SOURCE_STAT):])
            if ref_value is None:
                return False
            n = ref_value
        elif isinstance(n, str) and n.startswith(COUNT_STAT):  # -- control change (wave 20E) --
            n = len(candidates(plan, from_key(n[len(COUNT_STAT):]), you, source))
        elif isinstance(n, str) and n.startswith(SOURCE_COUNTERS):  # -- counters (wave 5H) --
            have = _source_counters(plan, source, n[len(SOURCE_COUNTERS):])
            if have is None:
                return False
            n = have
        elif n == COLORS_SPENT:  # (wave 25B) the source's payment record, as values reads it for "the number of colors of mana spent"
            from app.rules import values

            src = plan.state.cards.get(source or "")
            if src is None:
                return False
            n = values.evaluate(plan, {"controller": you, "source_card": src.id, "source_object": plan.oid(src)}, {"colors_spent": 1})
        elif n == X_VALUE:  # (107.3f: X is the one chosen for the spell; none known: nothing matches)
            src = plan.state.cards.get(source or "")
            x = src.stack_info.x if src is not None and src.stack_info is not None and src.stack_info.x is not None \
                else getattr(plan, "x_choice", None)  # (not on the stack yet: the X announced for it)
            if x is None:
                return False
            n = x
        value = _stat(ch, what)
        if what == "mv" and value is not None and zone == "stack" and card.stack_info is not None and card.stack_info.x:
            value += card.stack_info.x * ch.mana_cost.count("{X}")  # 202.3e: X on the stack is the value chosen
        if value is None or not isinstance(n, int) or not {"<=": value <= n, ">=": value >= n, "==": value == n, "<": value < n, ">": value > n}[op]:
            return False
    for extra in sel.extras:
        if extra == "not_event" and card.id == attacker:  # (wave 23B) the event's own object (``attacker``: attacker_of)
            return False
        if extra == "enchanted" and not _has_attached(plan, card, "Aura"):
            return False
        if extra == "equipped" and not _has_attached(plan, card, "Equipment"):
            return False
        if extra == "enchanted_or_equipped" and not (_has_attached(plan, card, "Aura") or _has_attached(plan, card, "Equipment")):
            return False
        # -- grammar (wave 11C) -- 700.9:a counter on it, equipped, or enchanted by an Aura its own controller controls
        if extra == "modified" and not (_has_counter(card, COUNTER_ANY) or _has_attached(plan, card, "Equipment") or any(
                c.attached_to == card.id and "Aura" in plan.ch(c).subtypes and c.controller == card.controller
                for c in plan.state.cards.values())):
            return False
        if extra in _NOT_EXTRAS and matches(plan, Selector(zones=sel.zones, card=sel.card, extras=(extra[4:],)), card, ch, you, source):
            return False  # (wave 15A)
        # (700.6; set only by the look-and-distribute grammar: "a historic card from among them")
        if extra == "historic" and not ("Artifact" in ch.types or "Legendary" in ch.supertypes or "Saga" in ch.subtypes):
            return False
        if extra.startswith("pot:"):  # (wave 15A) power or toughness (either) at most / at least n
            op, n = ("<=", int(extra[6:])) if extra[4:6] == "<=" else (">=", int(extra[6:]))
            vals = [v for v in (_stat(ch, "power"), _stat(ch, "toughness")) if v is not None]
            if not any(v <= n if op == "<=" else v >= n for v in vals):
                return False
        if extra == "basic_land_type" and not ch.subtypes & {"Plains", "Island", "Swamp", "Mountain", "Forest"}:
            return False  # (wave 20D)
        if extra.startswith("pts:"):  # -- put from hand (wave 19E) -- the power and toughness added (a * is no number: no match)
            pw, tg = _stat(ch, "power"), _stat(ch, "toughness")
            if pw is None or tg is None or not (pw + tg <= int(extra[6:]) if extra[4:6] == "<=" else pw + tg >= int(extra[6:])):
                return False
        if extra.startswith("counter:") and not _has_counter(card, extra[8:]):  # (wave 5H: any kind, "*")
            return False
        if extra.startswith("nocounter:") and _has_counter(card, extra[10:]):  # -- counters (wave 5H) --
            return False
        if extra.startswith("entered_this_turn") and not _entered_now(plan, card, you if extra.endswith("_you") else None):
            return False  # (wave 5H)
        if extra.startswith("all_colors:") and not set(extra[11:]) <= set(ch.colors):  # -- both colors (wave 6D) --
            return False
        if extra == "shares_color_source" and ((src := plan.state.cards.get(source or "")) is None or not plan.ch(src).colors & ch.colors):
            return False  # -- static_other sweep (wave 17C) -- conspire 702.78a: a creature that shares a color with the spell
        if extra.startswith("oid:") and plan.oid(card) != extra[4:]:  # (wave 18F) the granting object
            return False
        if extra == "shares_commander_type" and not _shares_commander_type_now(plan, ch, you):  # (wave 22E)
            return False
        if extra == "goaded":  # (wave 22E) 701.15b: goaded by someone (a goad effect lasts until that player's next turn: layers' imposed rules)
            from app.rules.keyword_actions import goaded_by

            if not goaded_by(ch):
                return False
        if extra.startswith("name:"):  # -- card names (wave 22B) -- 709.4a, a name chosen earlier in this resolution
            from app.rules import card_names

            if not card_names.has_name(ch, extra[5:]):
                return False
        if extra in ("crewed_it", "saddled_it"):  # (wave 23D)
            from app.rules import crew_saddle

            src = plan.state.cards.get(source or "")
            if src is None or not crew_saddle.tapped_for(plan, "crew" if extra == "crewed_it" else "saddle", plan.oid(card), plan.oid(src)):
                return False
        if extra == "named_self" and ((src := plan.state.cards.get(source or "")) is None or plan.ch(src).name != ch.name):
            return False  # (wave 12C)
        if extra == "attacking_you" and (card.attacking is None or card.attacking.kind != "player" or card.attacking.id != you):
            return False
        if extra in ("face_down", "face_up") and card.face_down != (extra == "face_down"):  # -- wave 3F --
            return False
        if extra == "morph_ability" and not {"morph", "megamorph"} & ch.keywords:
            return False
        if extra == "cycling_ability" and not any(k.endswith("cycling") for k in ch.keywords):  # (wave 20C)
            return False
        if extra == "unblocked" and card.id in plan.rules.blocked:  # (wave 15E) a blocked attacker stays blocked
            return False
        if extra == "attacked_this_turn" and not _attacked_this_turn_now(plan, card):  # -- combat (wave 5C) --
            return False
        if extra == "drawn_this_turn" and not drawn_now(plan, card):  # -- drawn this turn (wave 18G) --
            return False
        if extra in ("was_dealt_damage", "dealt_damage", "dealt_damage_you", "dealt_damage_by_source"):  # -- damage history (wave 6B) --
            from app.rules import damage_history

            if not damage_history.matches(plan, card, extra, you, source):
                return False
        if extra in ("blocking_source", "blocked_by_source"):  # -- damage wordings (wave 6B) -- the source's block now
            src = plan.state.cards.get(source or "")
            if src is None or not src.zone.endswith(":battlefield") or not card.zone.endswith(":battlefield"):
                return False
            if (not card.blocks(src.id)) if extra == "blocking_source" else (not src.blocks(card.id)):
                return False
        if extra == "has_adventure":  # (wave 25B) the printing is an adventurer card, whichever half it is as it is cast
            data = plan.info.get(card.card_id) if card.card_id else None
            if not (data and data.get("layout") == "adventure"):
                return False
        if extra == "greatest_power_own":  # -- damage wordings (wave 6B) -- the greatest power among creatures its
            # controller controls (Crackling Doom: what the sacrificing player may choose; ties all qualify)
            mine = _stat(ch, "power")
            others = [_stat(plan.ch(c), "power") for c in plan.state.cards.values()
                      if c.controller == card.controller and c.zone.endswith(":battlefield") and plan.ch(c).is_creature]
            if mine is None or any(p is None or p > mine for p in others):
                return False
        if extra == "x_cost" and "{X}" not in ch.mana_cost:  # -- activated wordings (wave 15D) -- (107.3: printed in its mana cost)
            return False
        if extra == "toughness_gt_power":  # -- damage wordings (wave 6B) -- as it is now (611.3a for a static)
            p, t = _stat(ch, "power"), _stat(ch, "toughness")
            if p is None or t is None or t <= p:
                return False
        if extra.startswith("subtype_any:") and not set(extra[12:].split("|")) & ch.subtypes:  # (wave 6C)
            return False
        if extra == "mergeable":  # -- merged permanents (wave 18D) -- a permanent a mutating spell can merge with (app/rules/merged.py)
            from app.rules import merged

            if not merged.mergeable(plan, card):
                return False
    # -- chosen type (wave 4J) --
    return not any(e in CHOSEN_EXTRAS for e in sel.extras) or _chosen_ok(plan, sel, ch, source)


def drawn_now(plan: Plan, card: CardInstance) -> bool:
    """-- drawn this turn (wave 18G) -- the card is still the object (400.7) its owner drew this turn, in their hand (PRIVATE: only
    ever read for the owner's own choices, never shown to another player)."""
    r = plan.state.rules
    if r is None or r.turn_log.turn != plan.state.turn.number or not card.zone.endswith(":hand"):
        return False
    return r.object_id(card.id) in r.turn_log.drawn.get(card.owner, ())


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
