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
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

PREFIX = "sel:"
CARD_TYPES = {"artifact": "Artifact", "creature": "Creature", "enchantment": "Enchantment", "land": "Land",
              "planeswalker": "Planeswalker", "battle": "Battle", "instant": "Instant", "sorcery": "Sorcery",
              "kindred": "Kindred"}
PERMANENT_TYPES = ("Artifact", "Creature", "Enchantment", "Land", "Planeswalker", "Battle")
SUPERTYPES = {"legendary": "Legendary", "basic": "Basic", "snow": "Snow"}
COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
KEYWORDS = ("flanking", "flying", "first strike", "double strike", "deathtouch", "lifelink", "vigilance", "trample", "haste",
            "reach", "menace", "indestructible", "hexproof", "defender", "shroud", "flash", "protection", "banding")
# Noncreature subtypes that appear in selectors (205.3g-k).
OTHER_SUBTYPES = {"Equipment", "Aura", "Vehicle", "Food", "Clue", "Treasure", "Blood", "Gold", "Saga", "Shrine",
                  "Curse", "Plains", "Island", "Swamp", "Mountain", "Forest", "Desert", "Gate", "Cave", "Town",
                  "Urza's", "Sphere", "Lesson", "Adventure", "Arcane", "Trap", "Room", "Class", "Case", "Background",
                  "Fortification", "Attraction", "Contraption", "Powerstone", "Map", "Incubator", "Junk",
                  "Lair", "Locus", "Bobblehead", "Cartouche", "Spacecraft", "Rune", "Plan", "Lander", "Planet"}  # (wave 25C: Rune, 205.3h; wave 35D: Plan, 205.3h)  # (Lair: the Dragon's Lair lands, "return a non-Lair land you control", wave 1B)
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
              "plains": "Plains", "pegasi": "Pegasus", "octopi": "Octopus", "octopuses": "Octopus", "harpies": "Harpy", "dryads": "Dryad"}
_IRREGULAR.update({"oxen": "Ox", "armies": "Army", "spies": "Spy", "cyclopes": "Cyclops"})  # -- static wordings (wave 6E) --
_IRREGULAR.update({"aurochs": "Aurochs"})  # -- trigger tail (wave 15B) -- (its own plural)
_IRREGULAR.update({"urza's": "Urza's", "urza’s": "Urza's"})  # 205.3i: possessive land subtype, never a plural
_IRREGULAR.update({"heroes": "Hero"})  # -- counters (wave 21D) --
_MARKERS = {"card", "spell", "perm", "token", "commander"}  # nouns that mark what kind of object, not its type
ZONES = ("battlefield", "graveyard", "hand", "exile", "library", "stack", "command")


@dataclass(frozen=True)
class Selector:
    player: str | None = None  # a player selector: "any" | "opponent" | "you"
    player_exclude: str | None = None  # event-bound "that_player" -> "player:<id>"
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
    attacking_player: str | None = None
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
    compare: tuple[tuple[str, str, int | float | str], ...] = ()  # ("mv"|"power"|"toughness", "<="|">="|"==", n) (str: wave 5H)
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
    lost_life_this_turn: bool = False
    damaged_by_source_this_turn: bool = False

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


# -- attached events (wave 30S) -- "target Aura or Equipment attached to a creature you control" (Halvar): what it is attached to (301.5, 303.4);
# before the controller suffix, whose "you control" is the host's
@_suffix(r"(?:that(?:'s| is) )?attached to a (?P<k>creature|permanent)(?P<you> you control)?")  # (wave 100F: "target Aura that's attached to a permanent", Aura Graft)
def _attached_to_creature(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, f"attached_{m['k']}" + ("_you" if m["you"] else "")))


# -- activated other (wave 34B) -- "Destroy all Auras attached to ~." (Hakim), "Sacrifice an Equipment attached to ~" (Ronin): what is attached to the source
# itself (301.5, 303.4), read against the ability's source as it is now (``source``); before the controller suffix, whose "you control" would be the host's
@_suffix(r"(?:that(?:'s| is| are) )?attached to ~")
def _attached_to_source(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "attached_source"))


# -- attack restrictions (wave 32B) -- "Each creature that's enchanted by an Aura you control can't attack you" (Eriette): an Aura on it that the effect's controller
# controls (303.4; unlike "modified", 700.9, the Aura's controller is "you", not the creature's); before the controller suffix, whose "you control" is the Aura's
@_suffix(r"that(?:['’]s| is| are) enchanted by an Aura you control")
def _enchanted_by_your_aura(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "enchanted_by_yours"))


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


# -- defending owner (wave 110C) -- "card in exile … that defending player owns" (Ravenloft Adventurer)
@_suffix(r"(?:that )?defending player owns")
def _defending_owns(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, owner="defending")


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


# -- block events (wave 53C) -- "Attach this Aura to target creature other than enchanted creature." (Kjeldoran Pride): not the creature the source is attached to
@_suffix(r"other than (?:enchanted|equipped) creature")
def _other_than_host(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "not_host_of_source"))


@_suffix(r"other than ~")
def _other_than_self(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, other=True)


# -- block events (wave 53C) -- 708.2: "can't be blocked by creatures that don't have a name" (Pompous Gadabout): a face-down permanent has no name
@_suffix(r"that (?:don['’]t|doesn['’]t) have a name")
def _nameless(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "nameless"))


@_suffix(r"that['’]s (?P<w>attacking or blocking|attacking|blocking|tapped|untapped)")
def _thats_status(s: Selector, m: re.Match[str]) -> Selector:
    s2 = _prefix(s, m["w"].replace(" ", "-"))
    assert s2 is not None
    return s2


# -- activated other (wave 42C) -- 506.5: "Target creature that's attacking alone gets +1/+1 until end of turn." (Viper, Cruel Conspirator), "Target creature you control
# that's attacking alone" (Crowd of True Believers): an attacking creature while no other creature is attacking
@_suffix(r"that['’]s attacking alone")
def _attacking_alone(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, attacking=True, extras=(*s.extras, "attacking_alone"))


@_suffix(r"that (?:isn['’]t|is not|aren['’]t|are not) attacking")  # -- as long as (wave 35D) -- 611.3a: Arcades Sabboth's "as long as it's not attacking"
def _not_attacking(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "not_attacking"))


@_suffix(r"controlled by a player who controls (?P<n>\w+) or fewer lands")  # -- statics (wave 110D) -- Sheltering Prayers: each one's own controller's land count
def _owner_few_lands(s: Selector, m: re.Match[str]) -> Selector:
    n = _NUMBERS.get(m["n"].lower())
    if n is None:
        raise ValueError("a number word")
    return replace(s, extras=(*s.extras, f"ctrl_lands_le:{n}"))


@_suffix(r"other than that (?:creature|permanent)")  # -- stack interaction (wave 23B) -- Pawpatch Recruit: not the object the trigger's event is about
def _other_than_event(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "not_event"))


@_suffix(r"that attacked you this turn")  # -- cards (wave 110F) -- 508.1 / 506.3: declared as an attacker of the player (not a planeswalker), TurnLog.attacked_who
def _attacked_you_this_turn(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "attacked_you_this_turn"))


@_suffix(r"that attacked this turn")  # -- combat (wave 5C) -- declared as attackers this turn (508.1; 508.4: not put)
def _attacked_this_turn(s: Selector, m: re.Match[str]) -> Selector:
    if re.search(r"\bcreatures(?: you control)?$", m.string[: m.start()]) is None:
        raise ValueError("only \"creatures that attacked this turn\" (a group on the battlefield)")
    return replace(s, extras=(*s.extras, "attacked_this_turn"))


# -- counters (wave 41A) -- "each creature you control that you've put one or more +1/+1 counters on this turn has hexproof" (Kid Loki): the permanent (400.7: not a
# new object) a counter of that kind was put on by you, 122.6, this turn (TurnFact "counters": ``object_id``, ``actor``, ``counter``)
@_suffix(r"that you've put one or more (?P<k>\+1/\+1|-1/-1|[a-z]+) counters on this turn")
def _you_put_counters_this_turn(s: Selector, m: re.Match[str]) -> Selector:
    if re.search(r"\bcreatures?(?: [a-z ]+? controls?)?$", m.string[: m.start()].rstrip()) is None:
        raise ValueError("only \"creatures that you've put counters on this turn\" (a group on the battlefield)")
    return replace(s, extras=(*s.extras, f"you_put_counters:{m['k']}"))


@_suffix(r"that didn't attack this turn")  # -- damage sized by a count (wave 34D) -- Kratos, Angel's Trumpet: not declared as an attacker this turn (508.1)
def _didnt_attack_this_turn(s: Selector, m: re.Match[str]) -> Selector:
    if re.search(r"\bcreatures?(?: [a-z ]+? controls?)?$", m.string[: m.start()].rstrip()) is None:  # ("creatures that player controls that didn't …"; wave 41A: "each creature you control that didn't …")
        raise ValueError("only \"creatures that didn't attack this turn\" (a group on the battlefield)")
    return replace(s, extras=(*s.extras, "didnt_attack_this_turn"))


# -- counters (wave 41A) -- "each creature you control that didn't attack or enter this turn" (The Fifth Doctor): neither declared as an attacker (508.1) nor
# entered the battlefield (a new object if it left and came back, 400.7) this turn
@_suffix(r"that didn't attack or enter this turn")
def _didnt_attack_or_enter_this_turn(s: Selector, m: re.Match[str]) -> Selector:
    if re.search(r"\bcreatures?(?: [a-z ]+? controls?)?$", m.string[: m.start()].rstrip()) is None:
        raise ValueError("only \"creatures that didn't attack or enter this turn\" (a group on the battlefield)")
    return replace(s, extras=(*s.extras, "didnt_attack_this_turn", "not_entered_this_turn"))


@_suffix(r"that blocked this turn")  # -- combat state (wave 27A) -- declared as blockers this turn (509.1g); a creature put onto the battlefield blocking never "blocked"
def _blocked_this_turn(s: Selector, m: re.Match[str]) -> Selector:
    if not m.string[: m.start()].endswith(("creature", "creatures")):
        raise ValueError("only \"creature(s) that blocked this turn\"")
    return replace(s, extras=(*s.extras, "blocked_this_turn"))


@_suffix(r"that attacked or blocked this turn")  # -- instead (wave 100K) -- Gideon's Triumph: declared as an attacker (508.1) or a blocker (509.1g) this turn
def _attacked_or_blocked_this_turn(s: Selector, m: re.Match[str]) -> Selector:
    if not m.string[: m.start()].endswith(("creature", "creatures", "creature of their choice")):
        raise ValueError("only \"creature(s) that attacked or blocked this turn\"")
    return replace(s, extras=(*s.extras, "attacked_or_blocked_this_turn"))


# -- combat history (wave 31D) -- 509.1g: which creature blocked which this turn (TurnLog.blocks, objects): "each creature that blocked or was
# blocked this turn" (Heat Stroke), "all creatures it blocked this turn" (Defiant Vanguard: those the source blocked)
@_suffix(r"that blocked or was blocked this turn")
def _involved_in_blocks(s: Selector, m: re.Match[str]) -> Selector:
    if not m.string[: m.start()].endswith(("creature", "creatures")):
        raise ValueError("only \"creature(s) that blocked or was blocked this turn\"")
    return replace(s, extras=(*s.extras, "block_involved_this_turn"))


@_suffix(r"(?:it|this creature|~) blocked this turn")
def _blocked_by_source_this_turn(s: Selector, m: re.Match[str]) -> Selector:
    if not m.string[: m.start()].endswith(("creature", "creatures")):
        raise ValueError("only \"creature(s) it blocked this turn\"")
    return replace(s, extras=(*s.extras, "blocked_by_source_this_turn"))


@_suffix(r"drawn this turn")  # -- drawn this turn (wave 18G) -- "cards in your hand drawn this turn" (Sylvan Library): TurnLog.drawn
def _drawn_this_turn(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "drawn_this_turn"))


@_suffix(r"with one or more (?P<c>white|blue|black|red|green) mana symbols? in its mana cost")  # -- trigger other (wave 44B) -- Namor the Sub-Mariner: 202.1, 107.4e
def _with_color_symbols(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "cost_symbol:" + COLORS[m["c"]]))


@_suffix(r"with another (?P<kind>Aura|Equipment) attached to it")
def _with_other_attachment(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "other_attachment:" + m["kind"]))


@_suffix(r"with a legendary Equipment attached to it")  # -- trigger other (wave 44B) -- Kassandra, Eagle Bearer: 301.5, an Equipment attached to it that is legendary
def _with_legendary_equipment(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "legendary_equipped"))


# -- both colors (wave 6D) -- "a spell that's both red and white" (the Mimics): each of the colors (105.2)
@_suffix(r"that['’]s both (?P<c1>" + "|".join(COLORS) + r") and (?P<c2>" + "|".join(COLORS) + r")")
def _thats_both(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "all_colors:" + COLORS[m["c1"]] + COLORS[m["c2"]]))


DEFENDED = "defended_player"  # -- triggers (wave 19B) -- a non-targeted "defending player controls": the attack event's player (bound as it's put on the stack)
THAT_PLAYER = "that_player"  # -- damage wordings (wave 6B) -- a controller the trigger event's player binds


@_suffix(r"who lost life this turn")
def _player_lost_life(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, lost_life_this_turn=True)


# -- damage history (wave 6B) -- "creature that was dealt damage this turn", "each creature dealt damage this turn",
# "creature that dealt damage [to you] this turn" (app/rules/damage_history.py)
@_suffix(r"that dealt combat damage to you this turn")  # -- trigger other (wave 39A) -- Witch-king of Angmar: "a creature of their choice that dealt combat damage to you this turn"
def _dealt_combat_damage_you(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "dealt_combat_damage_you"))


@_suffix(r"that dealt damage (?P<you>to you )?this turn")
def _dealt_damage_this_turn(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "dealt_damage_you" if m["you"] else "dealt_damage"))


# -- crew & saddle (wave 23D) -- "creature that crewed it this turn" / "that saddled it this turn": tapped this turn to pay a crew / saddle
# ability of the source (702.122c, 702.171c; app/rules/crew_saddle.py)
@_suffix(r"that (?P<k>crewed|saddled) (?:it|~|this (?:Vehicle|Mount|permanent)) this turn")
def _crewed_it(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "crewed_it" if m["k"] == "crewed" else "saddled_it"))


# -- counters (wave 26D) -- "each creature that convoked it": the creatures its spell's cost was paid with (702.51a, 601.2h payment record)
@_suffix(r"that convoked (?:it|~|this (?:creature|permanent))")
def _convoked_it(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "convoked_it"))


@_suffix(r"dealt damage by (?:this creature|~) this turn")  # -- damage history (wave 19E) -- "a creature dealt damage by ~ this turn"
def _dealt_damage_by_source(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "dealt_damage_by_source"))


@_suffix(r"(?:that (?:was|were|has been|have been) )?dealt damage this turn")  # (wave 53C: "has been dealt damage", Giant Shark)
def _was_dealt_damage_this_turn(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "was_dealt_damage"))


@_suffix(r"that player controls")  # "destroy target artifact that player controls" in a trigger about a player: bound
def _that_player_controls(s: Selector, m: re.Match[str]) -> Selector:  # to it as the trigger is put on the stack
    return replace(s, controller=THAT_PLAYER)  # (triggers.bind_that_player: "player:<id>"; unbound, nothing matches)


@_suffix(r"(?:that(?:'s| is) (?=blocking))?(?P<b>blocking (?:it|this creature|~)|(?:it['’]s|this creature is|~ is) blocking)")  # "target creature blocking it" / "… it's blocking": the source's
# (-- attached (wave 100F) -- also "that's blocking it": Arc Spitter's granted "{1}: This creature deals 1 damage to target creature that's blocking it.")
def _blocking_source(s: Selector, m: re.Match[str]) -> Selector:  # blocks (509.1; scripts._event_refs_ok: "it" is ~)
    return replace(s, extras=(*s.extras, "blocking_source" if m["b"].startswith("blocking") else "blocked_by_source"))


# -- combat history (wave 31D) -- "each creature blocking or blocked by this creature" (Kjeldoran Frostbeast, Greater Werewolf), "all creatures
# blocked by this creature" (Wall of Nets): the source's blocks as they stand (509.1; they still stand as the end of combat step begins)
@_suffix(r"(?P<b>blocking or (?:being )?blocked by|blocked by) (?:this creature|~)")  # (wave 53C: "blocking or being blocked by this creature", Sworn Defender)  # (named: "it" would need an antecedent, scripts._event_refs_ok)
def _block_pair_source(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "block_pair_this" if m["b"].startswith("blocking") else "blocked_by_this"))


@_suffix(r"that (?:has|have) an Adventure")  # -- trigger other (wave 25B) -- 715.1: the card is an adventurer card ("It doesn't need to have gone on the adventure first")
def _has_adventure(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "has_adventure"))


@_suffix(r"with \{[xX]\} in (?:its|their) mana costs?")  # -- activated wordings (wave 15D) -- "a spell with {X} in its mana cost" (107.3)
def _has_x_cost(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "x_cost"))


@_suffix(r"with mana cost (?P<c>\{[^}]+\}(?: or \{[^}]+\})*)")  # -- saga grants (wave 51B) -- Urza's Saga: "an artifact card with mana cost {0} or {1}" is the printed cost itself (202.1), not its mana value
def _mana_cost_is(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "cost_is:" + "|".join(m["c"].split(" or "))))


# -- static_other (wave 42A) -- "creatures you control with no abilities" / "creatures with abilities" (Jasmine Boreal of the Seven, Muraganda Petroglyphs, Ruxa): an
# object has an ability when any of its ability lines is there, the printed ones and the ones granted (113.1, 613.1f), judged on it as it is now
@_suffix(r"with no abilities")
def _no_abilities(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "no_abilities"))


@_suffix(r"with abilities")
def _has_abilities(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "has_abilities"))


# -- base power (wave 30J) -- 208.4b: a creature's base power and/or toughness are what its characteristic-defining ability (613.4a) and the effects
# that set them (613.4b) leave, ignoring effects and counters that modify without setting (Primo: "with base power 0"; Bess, Duskana: "with base
# power and toughness 1/1"; Kutzil, Ms. Marvel: "with power greater than its base power")
@_suffix(r"with base power(?: and toughness)? (?P<p>\d+)(?:/(?P<t>\d+))?")
def _base_pt(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, compare=(*s.compare, ("base_power", "==", int(m["p"])), *((("base_toughness", "==", int(m["t"])),) if m["t"] else ())))


@_suffix(r"(?:each )?with base power or toughness (?P<n>\d+)(?P<max> or less)?")
def _either_base_pt(s: Selector, m: re.Match[str]) -> Selector:
    op = "<=" if m["max"] else "=="
    return replace(s, extras=(*s.extras, f"base_pt_either:{op}:{m['n']}"))


@_suffix(r"with power greater than (?:its|their) base power")
def _power_over_base(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "power_gt_base"))


@_suffix(r"that (?:isn't|is not|aren't|are not) an? (?P<sub>[A-Z][A-Za-z]+(?:(?:, | or |, or )[A-Z][A-Za-z]+)*)")  # -- commanders (wave 47A) -- Heliod, the Radiant Dawn: "enchantment card that isn't a God" (a subtype, 205.3); wave 51C: a list, "that isn't a Kraken, Leviathan, or Serpent" - none of them
def _isnt_subtype(s: Selector, m: re.Match[str]) -> Selector:
    cores = [_core(w) for w in re.split(r", or |, | or ", m["sub"])]
    if any(core is None or core[0] != "sub" for core in cores):
        raise ValueError(m["sub"])
    return replace(s, not_subtypes=(*s.not_subtypes, *(core[1] for core in cores if core)))


@_suffix(r"with toughness greater than (?:its|their) power")  # (Ghalta the Immovable, Bedrock Tortoise)
def _toughness_over_power(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "toughness_gt_power"))
@_suffix(r"with power equal to (?:its|their) toughness")
def _equal_power_toughness(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "power_eq_toughness"))
# -- end damage history (wave 6B) --


@_suffix(r"(?:that(?:['’]s| are) )?attacking (?:one of )?your opponents(?P<pw> and/or planeswalkers they control)?")  # -- most-played cards II (wave 45A) -- Oviya, Automech Artisan: attacking a player who is an opponent of the source's controller (a planeswalker's controller isn't "attacked": 506.2)
def _attacking_opponent(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, attacking=True, extras=(*s.extras, "attacking_opponent_pw" if m["pw"] else "attacking_opponent"))


@_suffix(r"that's attacking a battle")  # -- instead (wave 100K) -- Rampaging Geoderm's "if it's attacking a battle": the attack is on a battle (310.5, 506.3)
def _attacking_battle(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, attacking=True, extras=(*s.extras, "attacking_battle"))


@_suffix(r"(?:that(?:['’]s| are) )?attacking you(?P<pw> or a planeswalker you control)?")  # (wave 17D: also plural / bare; wave 46C: "or a planeswalker you control", Soul Snare)
def _attacking_you(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, attacking=True, extras=(*s.extras, "attacking_you_pw" if m["pw"] else "attacking_you"))


_SUFFIXES.insert(0, _SUFFIXES.pop())  # (first: its "… you control" is also the controller suffix)


@_suffix(r"that['’]s exactly two colors")
def _exactly_two_colors(s: Selector, m: re.Match[str]) -> Selector:  # (wave 44C: Niv-Mizzet, Supreme) 105.2: two of the five colors, no more and no fewer
    return replace(s, extras=(*s.extras, "two_colors"))


# -- trigger lines (wave 100A) -- Invasion of Ravnica "that isn't exactly two colors" (105.2: colorless, one, three or more colors); Gilt-Leaf
# Winnower "whose power and toughness aren't equal" (208.1: its current values); Witchbane Orb "Curses attached to you" (303.4, 702.5d: an Aura enchanting the player)
@_suffix(r"that (?:isn['’]t|is not) exactly two colors")
def _not_two_colors(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "not_two_colors"))


@_suffix(r"whose power and toughness aren['’]t equal")
def _pt_unequal(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "power_ne_toughness"))


@_suffix(r"attached to you")
def _attached_to_you(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "attached_you"))


# (Kitesail Skirmisher) "another target creature attacking the same player or planeswalker": 508.1b, 506.3 — the one the source attacks, as it is now
# or as the source last existed (608.2h); a battle is neither, so beside a source attacking a battle nothing matches
@_suffix(r"attacking the same player or planeswalker")
def _attacking_same(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, attacking=True, extras=(*s.extras, "attacking_same100a"))


def _attacking_same100a(plan: Plan, card: CardInstance, source: str | None) -> bool:
    src = plan.state.cards.get(source or "")
    if src is None or card.attacking is None or card.id == src.id:
        return False
    if src.zone.endswith(":battlefield"):
        on = f"{src.attacking.kind}:{src.attacking.id}" if src.attacking is not None else None
    else:
        last = plan.rules.last_known(src.id)
        on = last.attack_on if last is not None else None
    if on is None or on != f"{card.attacking.kind}:{card.attacking.id}":
        return False
    if card.attacking.kind == "player":
        return True
    walker = plan.state.cards.get(card.attacking.id)
    return walker is not None and "Planeswalker" in plan.ch(walker).types


@_suffix(r"that(?:['’]s| is| are) (?P<list>(?:" + "|".join(COLORS) + r")(?:, (?:" + "|".join(COLORS) + r"))*(?:,? or (?:" + "|".join(COLORS) + r"))?)")
def _thats_colored(s: Selector, m: re.Match[str]) -> Selector:  # (wave 19D: "that's white, blue, black, or red")
    found = tuple(COLORS[c] for c in re.findall("|".join(COLORS), m["list"]))
    return replace(s, colors=(*s.colors, *found))


# -- token & pump wordings (wave 6C) -- "each other creature you control that's a Fungus or Saproling", "each creature that's
# a Barbarian, a Warrior, or a Berserker": any of these creature types (205.3m)
# (-- counters (wave 33C) -- "each other creature you control that's a token or a Rabbit" (Finneas, Ace Archer): "token" is one of the alternatives, kept
# as the word in the list and read as the object's being a token (111.7); alone it is no creature type: "that's a token" stays unread)
# (-- cant restrictions (wave 46A) -- "each creature you control that's an artifact or Human" (Paladin Danse): a card type is one of the alternatives too, read from the object's types)
_THAT_WORD = r"[A-Z][\w'’-]*|token|artifacts?|creatures?|enchantments?|lands?|planeswalkers?|battles?"  # (wave 51A: "creature or Vehicle", Ao, the Dawn Sky)


# (-- commander sweep (wave 49B) -- plural: "permanents you control that are Spirits and/or enchantments" (Katilda), "creatures you control that are Fungi and/or Saprolings" (The Mycotyrant))
@_suffix(rf"that(?:['’]s| are) (?P<list>(?:an? )?(?:{_THAT_WORD})(?:(?:,|,? or|,? and/or) (?:an? )?(?:{_THAT_WORD}))*)")
def _thats_types(s: Selector, m: re.Match[str]) -> Selector:
    words = [w for w in re.split(r",? (?:or|and/or) |, ", m["list"]) if w]
    subs = [("tok", "token") if re.sub(r"^an? ", "", w) == "token" else _core(re.sub(r"^an? ", "", w)) for w in words]
    found = [c for c in subs if c is not None and c[0] in ("sub", "tok", "type")]
    if not subs or len(found) != len(subs) or found == [("tok", "token")] or (len(subs) < 2 and found[0][0] == "type"):
        raise ValueError("not a list of creature types")
    return replace(s, extras=(*s.extras, "subtype_any:" + "|".join(c[1] for c in found)))


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


@_suffix(r"you own but don't control")  # -- lines (wave 110D) -- 108.3 / 110.2: you own it, another player controls it (Coveted Falcon)
def _own_not_control(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, controller="opponent", owner="you")


@_suffix(r"you own")
def _you_own(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, owner="you")


@_suffix(r"(?:an opponent owns|your opponents own|you don't own|(?:is |are )?owned by (?:another player|an opponent))")  # (wave 25B: owned by another player; 30N: Umbris)
def _opp_own(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, owner="opponent")


@_suffix(r"you control but don't own")  # -- trigger other (wave 25B) -- 108.3 / 110.2: you control it, another player owns it (Edea)
def _control_not_own(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, controller="you", owner="opponent")


@_suffix(r"(?:from|in) your (?P<z>graveyard|hand|library)")
def _your_zone(s: Selector, m: re.Match[str]) -> Selector:
    return _in_zone(s, m["z"], "you")


@_suffix(r"from your hand (?:or|and/or) graveyard")  # -- reanimation (wave 37B) -- "an Aura or Equipment card from your hand or graveyard" (Danitha): two zones, both yours
def _your_hand_or_graveyard(s: Selector, m: re.Match[str]) -> Selector:
    if s.zones != _DEFAULT.zones:
        raise ValueError("conflicting zones")
    return replace(s, zones=("hand", "graveyard"), zone_owner="you", card=True)


@_suffix(r"(?:from|in) (?:a|any) graveyard")
def _any_graveyard(s: Selector, m: re.Match[str]) -> Selector:
    return _in_zone(s, "graveyard", None)


@_suffix(r"(?:from|in) defending player's graveyard")
def _defending_players_graveyard(s: Selector, m: re.Match[str]) -> Selector:
    return _in_zone(s, "graveyard", DEFENDED)


@_suffix(r"(?:from|in) that player's graveyard")  # -- if you do (wave 15C) -- the player a trigger is about (bound like
def _that_players_graveyard(s: Selector, m: re.Match[str]) -> Selector:  # "that player controls": triggers.bind_that_player)
    return _in_zone(s, "graveyard", "that_player")


@_suffix(r"(?:from|in) (?:an opponent's|your opponents') graveyards?")
def _opp_graveyard(s: Selector, m: re.Match[str]) -> Selector:
    return _in_zone(s, "graveyard", "opponent")


@_suffix(r"(?:from|in) (?:graveyards|each graveyard|all graveyards)")  # (wave 53B: "each card named ~ in each graveyard", 400.1: every player's)
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


@_suffix(r"with (?P<what>mana value|power|toughness) less than [xX]")  # -- cost reductions paid with objects (wave 47C) -- "target creature with mana value less than X" (March of Burgeoning Life)
def _less_than_x(s: Selector, m: re.Match[str]) -> Selector:  # (107.3f: the X of the spell, strictly; "X or less" is ``_compare``)
    return replace(s, compare=(*s.compare, ({"mana value": "mv", "power": "power", "toughness": "toughness"}[m["what"]], "<", X_VALUE)))


OWN_COUNTERS = "own_counters:"  # -- counters (wave 110I) -- the counters of that kind on the object tested
OWN_GRAVEYARD = "own_gy"  # -- most-played modal spells (wave 50I) -- the number of cards in the graveyard of the controller of the object tested


YOUR_HAND = "your_hand"  # -- most-played cards IV (wave 51G) -- the number of cards in the hand of the player the ability or static belongs to (402.3: a public count)


def _your_hand(s: Selector, m: re.Match[str]) -> Selector:  # (Ensnaring Bridge)
    return replace(s, compare=(*s.compare, ({"mana value": "mv", "power": "power", "toughness": "toughness"}[m["what"]],
                                            {"less than or equal to": "<=", "less than": "<", "greater than or equal to": ">=", "greater than": ">"}[m["op"]], YOUR_HAND)))


_SUFFIXES.insert(0, (re.compile(r"(?:,)? with (?P<what>power|toughness|mana value) (?P<op>less than or equal to|less than|greater than or equal to|greater than) the number of cards in your hand$"),
                     _your_hand))  # (first: "in your hand" is also the zone suffix)


@_suffix(r"with (?P<what>mana value|power|toughness) less than or equal to the number of cards in its controller's graveyard")  # (Drown in the Loch)
def _own_graveyard(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, compare=(*s.compare, ({"mana value": "mv", "power": "power", "toughness": "toughness"}[m["what"]], "<=", OWN_GRAVEYARD)))


@_suffix(r"with (?P<what>mana value|power|toughness) less than or equal to the number of (?P<kind>[a-z]+) counters on it")  # -- counters (wave 110I) -- Corrosion
def _own_counters(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, compare=(*s.compare, ({"mana value": "mv", "power": "power", "toughness": "toughness"}[m["what"]], "<=", OWN_COUNTERS + m["kind"])))


@_suffix(r"with power or toughness (?P<n>\d+) or (?P<dir>less|greater)")  # (wave 15A: Tetsuko Umezawa — either one)
def _power_or_toughness(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, f"pot:{'<=' if m['dir'] == 'less' else '>='}{m['n']}"))


# -- trigger sweep (wave 27B) -- "a creature spell with mana value 4, 5, or 6", "with power 2 or 3": one of the listed values (107.1: whole numbers)
@_suffix(r"with (?P<what>mana value|power|toughness) (?P<vals>\d+(?:, \d+)*,? or \d+)")
def _one_of_values(s: Selector, m: re.Match[str]) -> Selector:
    vals = sorted({int(v) for v in re.findall(r"\d+", m["vals"])})
    return replace(s, extras=(*s.extras, f"in:{ {'mana value': 'mv'}.get(m['what'], m['what']) }:{','.join(map(str, vals))}"))


@_suffix(r"with a basic land type")  # -- tutor (wave 20D) -- 205.3i: "a land card with a basic land type" (Nervous Gardener, Perilous Forays)
def _basic_land_type(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "basic_land_type"))


@_suffix(r"that shares a color with a legendary creature you control")
def _shares_legendary_creature_color(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, 'shares_color_legendary_creature_you_control'))


_SUFFIXES.insert(0, _SUFFIXES.pop())  # Its inner 'you control' is not the candidate's controller.


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
RESOLUTION_STAT = "resolution:"
ENERGY_PAID_STAT = RESOLUTION_STAT + "energy_paid"


@_suffix(r"with (?P<what>mana value|power|toughness) (?P<op>less than or equal to|less than|equal to|greater than or equal to|greater than) the amount of \{E\} paid this way")
def _compare_energy_paid(s: Selector, m: re.Match[str]) -> Selector:
    # CR 107.14, 608.2c: the paid amount is known during resolution, not when selecting targets.
    return replace(s, compare=(*s.compare, (_REF_STAT[m["what"]], _REF_OPS[m["op"]], ENERGY_PAID_STAT)))


@_suffix(r"with (?P<what>mana value|power|toughness) (?P<op>less than or equal to|less than|equal to|greater than or equal to|"
         r"greater than) (?:~|this creature)'s(?: (?P<ref>mana value|power|toughness))?")
def _compare_source(s: Selector, m: re.Match[str]) -> Selector:
    if m["ref"] is None and m["what"] == "mana value":
        raise ValueError("incomplete reference")  # ("mana value less than ~'s": which characteristic?)
    ref = m["ref"] or m["what"]  # ("power less than Mirko's": the same characteristic)
    return replace(s, compare=(*s.compare, (_REF_STAT[m["what"]], _REF_OPS[m["op"]], SOURCE_STAT + _REF_STAT[ref])))


# -- most-played cards II (wave 45A) -- "Destroy all creatures with power greater than target creature's power." (Fell the Mighty), "… less than that creature's power"
# (Mandate of Abaddon): the stat of the spell's one target creature as the spell resolves (effects._cards binds it; a definition without that target is refused)
TARGET_STAT = "tgt:"


@_suffix(r"with (?P<what>power|toughness) (?P<op>less than|greater than) (?:target|that) creature's (?P<ref>power|toughness)")
def _compare_target(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, compare=(*s.compare, (m["what"], _REF_OPS[m["op"]], TARGET_STAT + m["ref"])))


@_suffix(r"with (?P<eq>equal or )?lesser (?P<what>mana value|power|toughness)(?: than the creature that died)?")
def _compare_event(s: Selector, m: re.Match[str]) -> Selector:
    # -- reanimation (wave 16F) -- "return target creature card with lesser mana value from your graveyard" (Jackdaw Savior,
    # Riveteers Ascendancy): less than the object the trigger is about (the creature that died / was sacrificed), as it last
    # existed (608.2h); triggers.bind_event_stat swaps in the number as the ability goes on the stack (an unbound one matches nothing)
    return replace(s, compare=(*s.compare, (_REF_STAT[m["what"]], "<=" if m["eq"] else "<", EVENT_STAT + _REF_STAT[m["what"]])))


@_suffix(r"with mana value (?P<op>less than or equal to|less than) the number of counters on that creature")
def _compare_event_counters(s: Selector, m: re.Match[str]) -> Selector:
    # -- lines (wave 110D) -- Puca's Covenant: the counters the creature the trigger is about had as it last existed (608.2h), bound in triggers.bind_event_stat
    return replace(s, compare=(*s.compare, ("mv", _REF_OPS[m["op"]], EVENT_STAT + "counters")))


@_suffix(r"with that spell's mana value")  # (-- event spells (wave 36A) -- the same comparison, worded short: Infernal Kirin, Celestial Kirin)
@_suffix(r"with mana value equal to that spell's mana value")
def _compare_event_spell(s: Selector, m: re.Match[str]) -> Selector:
    # -- event spells (wave 28D) -- "return target creature card with mana value equal to that spell's mana value from your graveyard to your
    # hand" (Krile Baldesion): the spell the trigger is about, read as the ability goes on the stack (triggers.bind_event_stat; 202.3e: an X in
    # its cost counts what was chosen for it)
    return replace(s, compare=(*s.compare, ("mv", "==", EVENT_STAT + "mv")))


@_suffix(r"with mana value (?P<op>less than or equal to|less than|greater than or equal to|greater than) that spell's mana value")
def _compare_event_spell_ops(s: Selector, m: re.Match[str]) -> Selector:
    # -- trigger other (wave 52B) -- "return up to one target nonland permanent an opponent controls with mana value less than or equal to that spell's mana value to its
    # owner's hand" (Hammerhead Tyrant): the same binding as "equal to that spell's mana value" above, another comparison
    return replace(s, compare=(*s.compare, ("mv", _REF_OPS[m["op"]], EVENT_STAT + "mv")))


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
                  "modular", "toxic", "mutate", "awaken", "cascade", "flanking",  # (wave 39A: "all attacking creatures with flanking", Telim'Tor)
                  "plainswalk", "islandwalk", "swampwalk", "mountainwalk", "forestwalk",
                  "doctor's companion", "unearth")  # (wave 44B: "creature spell with doctor's companion", Rose Noble)  # (wave 26A: "creatures with plainswalk")  # (wave 21D: "a spell with cascade")  # (wave 20C: toxic/mutate/awaken; wave 19D: "each creature you control with modular": a printed keyword line; level up is rewritten into
# an activated ability and statics by app/rules/levelers.py, so it is no keyword of the object and stays unread)


@_suffix(r"with (?P<a>" + "|".join(_WITH_KEYWORDS) + r") or (?P<b>" + "|".join(_WITH_KEYWORDS) + r")")  # (wave 45D: "creatures you control with flash or haste", Sonic, Shadow)
def _with_kw_any(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, f"any_kw:{m['a']},{m['b']}"))  # either keyword


# -- commanders (wave 50C) -- "creature you control with flying, deathtouch, and/or lifelink" (Henrika Domnathi): any of the keywords listed
@_suffix(r"with (?P<list>(?:(?:" + "|".join(_WITH_KEYWORDS) + r"), )+(?:and/or|or) (?:" + "|".join(_WITH_KEYWORDS) + r"))")
def _with_kw_list(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "any_kw:" + ",".join(re.split(r", (?:and/or |or )?|, ", m["list"]))))


@_suffix(r"(?:with|that has) (?P<kw>" + "|".join(_WITH_KEYWORDS) + r")")  # (wave 15B: "a spell that has convoke")
def _with_kw(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, with_keywords=(*s.with_keywords, m["kw"]))


@_suffix(r"with foretell")
def _with_foretell(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, 'has_foretell'))


@_suffix(r"with flashback")
def _with_flashback(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "has_flashback"))


@_suffix(r"with (?:a|an) mana abilit(?:y|ies)")  # (wave 45D) 605.1a: an activated ability that could add mana ("creatures you control with a mana ability", Raggadragga)
def _with_mana_ability(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "mana_ability"))


@_suffix(r"without mana abilit(?:y|ies)")  # -- (wave 110C) -- 605.1a: "artifacts without mana abilities" (Midnight Arsonist)
def _without_mana_ability(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "no_mana_ability"))


@_suffix(r"(?:that )?(?:was|were) turned face up this turn")  # -- cards (wave 110F) -- 708.8: Kaust, Eyes of the Glade
def _turned_up_this_turn(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "turned_up_this_turn"))


@_suffix(r"with an activated ability that isn't a mana ability")  # -- cards (wave 110F) -- 602.1, 605.1a: Ravager Wurm
def _with_nonmana_ability(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "nonmana_ability"))


@_suffix(r"(?:that )?has an activated ability with \{T\} in its cost")  # -- activated other (wave 52D) -- Magewright's Stone: 602.1, a mana ability is an activated ability too (605.1a)
def _with_tap_ability(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "tap_ability"))


@_suffix(r"with (?:a )?(?:cycling|cycling abilit(?:y|ies))")  # -- reanimation (wave 20C) -- 702.29f: typecycling abilities are cycling abilities (wave 32C: "a cycling ability", Rooting Moloch)
def _with_cycling(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "cycling_ability"))


@_suffix(r"with (?:a )?kicker abilit(?:y|ies)")  # -- cast keywords (wave 43D) -- 702.33: "a kicker ability" includes the multikicker variant (702.33c; Coralhelm Chronicler's ruling)
def _with_kicker(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "kicker_ability"))


@_suffix(r"with (?:an? morph ability|morph abilities)")  # -- hidden exile (wave 18A) -- 702.37b: megamorph is a morph ability too
def _with_morph(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "morph_ability"))


# (-- static_other (wave 36B) -- "creatures without flying or reach" (Sidar Kondo) have neither: without_keywords is a list none of which it has)
@_suffix(r"without (?P<kw>" + "|".join(_WITH_KEYWORDS) + r")(?P<more>(?: or (?:" + "|".join(_WITH_KEYWORDS) + r"))*)")
def _without_kw(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, without_keywords=(*s.without_keywords, m["kw"], *(k for k in m["more"].split(" or ") if k)))


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


@_suffix(r"(?:with no |without (?:an? |any )?|(?:that )?(?:doesn't|don't|does not|do not) have (?:an? |any )?)" + _CK + r"counters? on (?:it|them)")
def _without_counters(s: Selector, m: re.Match[str]) -> Selector:  # (wave 30L: "that doesn't have a +1/+1 counter on it", Coiling Stalker)
    return replace(s, extras=(*s.extras, f"nocounter:{m['c'] or COUNTER_ANY}"))


# -- counter counts (wave 30L) -- "creatures you control with three or more +1/+1 counters on them" (Runadi), "a creature with three or
# more level counters on it" (Champion's Drake): how many counters of a kind it has (122.1)
@_suffix(r"with (?P<n>\d+|one|two|three|four|five|six|seven|eight|nine|ten) or more (?P<c>\+1/\+1|-1/-1|[a-z]+) counters on (?:it|them)")
def _with_n_counters(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, f"counter:{m['c']}>={_n(m['n'])}"))


COUNTER_ANY = "*"
SOURCE_COUNTERS = "counters:"  # a comparison with the number of a kind of counters on the source (as it last existed)
# -- control change (wave 20E) -- "target creature with power less than or equal to the number of creatures you control" (Beguiler of
# Wills), "… with mana value less than or equal to the number of Vampires you control" (Dominating Vampire): a comparison with the
# number of permanents the ability's controller controls that fit a selector, counted when the target is chosen and again as it resolves
COUNT_STAT = "cnt:"
_COUNT_CMP = re.compile(r"(?:,)? with (?P<what>mana value|power|toughness) (?P<op>less than or equal to|less than|greater than or equal to|greater than) the number of "  # (wave 50J: greater, Lavinia)
                        r"(?P<k>[A-Za-z' -]+? you control)$")


def _compare_count(s: Selector, m: re.Match[str]) -> Selector:
    counted = parse(m["k"])
    if counted is None or counted.player is not None or counted.card or counted.zones != ("battlefield",) or counted.controller != "you" \
            or counted.compare or counted.extras:
        raise ValueError("a count this comparison doesn't read")
    return replace(s, compare=(*s.compare, ({"mana value": "mv", "power": "power", "toughness": "toughness"}[m["what"]],
                                            {"less than or equal to": "<=", "less than": "<", "greater than or equal to": ">=", "greater than": ">"}[m["op"]], COUNT_STAT + counted.key())))


_SUFFIXES.insert(0, (_COUNT_CMP, _compare_count))  # (first: "… you control" is also the controller suffix)


# -- attached (wave 100F) -- "target creature with power less than the number of cards in your graveyard" (Temporary Insanity): the same comparison with
# the number of cards in the ability's controller's graveyard, counted when the target is chosen and again as it resolves (608.2b)
def _power_below_graveyard(s: Selector, m: re.Match[str]) -> Selector:
    counted = Selector(card=True, zone_owner="you", zones=("graveyard",))
    return replace(s, compare=(*s.compare, ("power", "<", COUNT_STAT + counted.key())))


_SUFFIXES.insert(0, (re.compile(r" with power less than the number of cards in your graveyard$"), _power_below_graveyard))  # (before the zone suffix)


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


# -- tutor (wave 47D) -- "Dragon cards not named ~" (Tiamat): a name other than the source's (201.2); before "named ~", whose pattern ends the same way
@_suffix(r"not named ~")
def _not_named_self(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "not_named_self"))


# -- amounts (wave 12C) -- "cards named ~ in all graveyards" (Kindle): the source's name (201.2), read with the source in play
@_suffix(r"that wasn't cast from its owner's hand")
def _not_cast_from_owner_hand(s: Selector, m: re.Match[str]) -> Selector:
    if re.search(r"\bspells?$", m.string[:m.start()]) is None:
        raise ValueError("cast origin only describes a spell")
    return replace(s, extras=(*s.extras, "not_cast_from_owner_hand"))


@_suffix(r"(?P<negative>not )?named (?P<name>[A-Z][^\n]+)")
def _named_literal(s: Selector, m: re.Match[str]) -> Selector:
    if ", then " in m["name"]:
        raise ValueError("an instruction separator is not part of a literal card name")
    return replace(s, extras=(*s.extras, ("not_name:" if m["negative"] else "name:") + m["name"]))


@_suffix(r"named ~")
def _named_self(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "named_self"))


# -- same name (wave 32A) -- "creature with the same name as ~" (Evil Twin, Callidus Assassin, Mocking Doppelganger), "creatures you control that
# don't have the same name as ~" (Marvin), "enchantment you control that doesn't have the same name as another permanent you control" (Yenna),
# "creature that doesn't have the same name as a token you control" (The Apprentice's Folly). 201.2a: two objects have the same name if they
# have a name in common; an object with no name (face down, 708.2a) has the same name as nothing, so "doesn't have the same name" holds of it
# (201.2c's "different name" would not: that wording isn't read). Names are the objects' own, layers applied (a copy has the copied name).
_SN_REF = r"(?:(?:another|a) (?:permanent|creature|token) you control|a (?:creature )?card in (?:your|their) graveyard)"


@_suffix(r"(?:with|(?:that |which )?(?:(?P<no>doesn't|don't|does not|do not) have|has|have)) the same name as "
         rf"(?P<ref>~|(?:the exiled card|a card exiled with ~)|{_SN_REF}(?: or {_SN_REF})?)")
def _same_name(s: Selector, m: re.Match[str]) -> Selector:
    if m["ref"] == "~":
        return replace(s, extras=(*s.extras, "nosamename_src" if m["no"] else "samename_src"))
    if m["ref"] in ("the exiled card", "a card exiled with ~"):  # (607.2a: the cards the linked ability exiled; "exiled_with" in the extra marks the
        if m["no"]:  # definition as referring to them, exiled_with.link)
            raise ValueError("not the exiled card's name")
        return replace(s, extras=(*s.extras, "samename_exiled_with"))
    refs = m["ref"].split(" or ")
    if len(refs) > 1 and not m["no"]:
        raise ValueError("same name as either")  # (a name shared with one of two sets: not read; "doesn't" is both sets' none)
    extras = []
    for r in refs:  # "another permanent you control": any other such object (the object itself never counts); "their graveyard": its controller's
        x = _parse(r.split(" ", 1)[1].replace("their graveyard", "your graveyard"))
        if x is None:
            raise ValueError("same name reference")
        extras.append(("no" if m["no"] else "") + ("samename_their:" if "their" in r else "samename_among:") + x.key())
    return replace(s, extras=(*s.extras, *extras))


_SUFFIXES.insert(0, _SUFFIXES.pop())  # (first: its "… you control" is also the controller suffix)


def _same_name_now(plan: Plan, extra: str, card: CardInstance, ch: Characteristics, you: str, source: str | None) -> bool:
    """The test of ``_same_name``'s extras (201.2a)."""
    from app.rules import card_names, exiled_with

    pos = extra.startswith("samename")
    kind = extra.removeprefix("no").removeprefix("samename_")
    src = plan.state.cards.get(source or "")
    if kind.startswith('object:'):
        from app.rules import context

        reference = json.loads(kind.partition(':')[2])
        found = context.info(plan, {'refs': {'name_reference': {'kind': 'objects', 'objects': [reference] if reference else []}}}, 'name_reference')
        same = found is not None and card_names.share(ch, found[1])
    elif kind == "src":
        same = src is not None and card_names.share(ch, plan.ch(src))
    elif kind == "exiled_with":  # (the linked ability's cards, as they are in exile: of the source that is still on the battlefield)
        same = src is not None and src.zone.endswith(":battlefield") and any(
            card_names.share(ch, plan.ch(plan.state.cards[c])) for c in exiled_with.cards(plan, {"source_object": plan.oid(src)})
            if not plan.state.cards[c].face_down)  # (406.3a: a card exiled face down has no name to compare, and nobody learns it from a trigger)
    else:
        who, _, key = kind.partition(":")
        # (review 33: only the object itself is left out, 400.7: read as it last existed (Guardian Project's entering creature, gone by the
        # time its ability resolves), the card is a new object: in the graveyard, or back on the battlefield, it shares that name, per its rulings)
        same = any(not (c == card.id and plan.state.cards[c] in (card,)) and card_names.share(ch, plan.ch(plan.state.cards[c]))
                   for c in candidates(plan, from_key(key), card.controller if who == "their" else you, source))
    return same == pos


# -- history (wave 22E) -- "a creature spell that shares a creature type with your commander" (Path of Ancestry): one of the creature types
# of one of the matcher's commanders (903.3: the cards its owner's deck names, wherever they are), read as the cards are
# -- most-played cards (wave 43B) -- "for each other attacking creature that shares a creature type with it" (Shared Animosity): one of the creature types of the
# object "it" names (205.3m) — the source, or (scripts: ``shares_type_event``) the creature the trigger is about; "other" leaves that object out (the ``source``)
@_suffix(r"that shares? a creature type with (?:it|this creature|~)")  # (-- trigger other (wave 52B) -- "the number of creatures you control that share a creature type with it", Mana Echoes)
def _shares_type_source(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "shares_type_source"))


@_suffix(r"that shares? a (?P<k>color|creature type) with equipped creature")  # -- wave 110A -- Konda's Banner: the creature this Equipment is attached to
def _shares_host(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "shares_" + ("color" if m["k"] == "color" else "type") + "_host110a"))


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


# -- wave 110A -- "target nonblack creature that entered since your last turn ended" (Premature Burial): an object numbered after the counter value
# stored when its controller's last turn ended (engine.start_next_turn). 400.7: a permanent that left and came back is a new object.
@_suffix(r"that could produce \{C\}")
def _could_produce_c(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "could_produce_c"))  # -- wave 110A -- Obsidian Charmaw


@_suffix(r"that entered since your last turn ended")
def _entered_since_my_turn(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "entered_since_my_turn"))


def _entered_now(plan: Plan, card: CardInstance, you: str | None) -> bool:
    from app.rules.history import log_for

    if not card.zone.endswith(":battlefield"):
        return False
    oid = plan.oid(card)
    return any(e.object_id == oid and (you is None or e.controller == you) for e in log_for(plan, False).entered)


# -- graveyard history (wave 36A) -- "target creature card in your graveyard that was put there from the battlefield this turn" (Moira, Samwise),
# "… from anywhere …" (Night Nurse, Garna), "… from their library …" (Captain N'ghathrod), "creature cards that were put into your graveyard from
# the battlefield this turn" (Fell Shepherd), "a card in a graveyard that was discarded or put there from a library this turn" (Ghost of Ramirez
# DePietro), "… that wasn't put there this combat" (Storrev): the card that is in that graveyard now is the object (400.7) that was put there then,
# read of the turn's log (RulesState.turn_log.entered_graveyard: where it came from, in which combat). Never a token (111.1: no card).
_PUT_FROM = {"the battlefield": "battlefield", "anywhere": "any", "a library": "library", "your library": "library", "their library": "library",
             "its owner's library": "library"}
_PUT_THERE = (r"that (?:was|were) (?:(?P<disc>discarded or )?put (?:there|into (?P<who>your|a|an opponent's|that player's) graveyard)) from "
              r"(?P<from>the battlefield|anywhere|a library|your library|their library|its owner's library) this turn")


@_suffix(_PUT_THERE)
def _put_there_this_turn(s: Selector, m: re.Match[str]) -> Selector:
    origin = _PUT_FROM[m["from"]]
    if m["disc"]:
        if origin != "library":
            raise ValueError("only \"discarded or put there from a library\"")
        origin = "discard_or_library"
    if m["who"]:  # the zone is the clause's own ("were put into your graveyard"), not an earlier "in your graveyard"
        s = _in_zone(s, "graveyard", {"your": "you", "a": None, "an opponent's": "opponent", "that player's": "that_player"}[m["who"]])
    return replace(s, extras=(*s.extras, "put_there:" + origin))


# -- activated other (wave 42C) -- "target creature card in a graveyard that was milled this turn" (The Master, Transcendent; Tato Farmer): 701.17a, the same fact as Raul's
@_suffix(r"that (?:was|were) milled this turn")
def _milled_this_turn(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "put_there:milled"))


@_suffix(r"that wasn't put there this combat")
def _not_put_there_this_combat(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "not_put_there_combat"))


def _put_there_now(plan: Plan, card: CardInstance, spec: str) -> bool:
    return put_there_state(plan.state, card, spec)


def put_there_state(state: GameState, card: CardInstance, spec: str) -> bool:
    """Is this card (in a graveyard now) the object that was put there this turn, from where ``spec`` says? (400.7, 608.2b)
    -- free cast (wave 40D) -- also "not_battlefield" ("from anywhere other than the battlefield": Banon, the Returners' Leader) and "milled" (701.17a: put there
    from a library by a mill instruction, a fact the turn's log keeps of that object — not by a search or another effect, Raul's ruling 2024-03-08)."""
    from app.game.state import COMBAT_PHASES

    r = state.rules
    if r is None or r.turn_log.turn != state.turn.number or not card.zone.endswith(":graveyard"):
        return False
    oid = r.object_id(card.id)
    arrival = next((a for a in reversed(r.turn_log.entered_graveyard) if a.card == card.id and a.object_id == oid), None)
    if arrival is None:  # (another object, or put there before this was recorded: an older save)
        return False
    if spec == "combat":  # 506.1: this combat phase (a turn may have several)
        return state.turn.phase in COMBAT_PHASES and r.combats > 0 and arrival.combat == r.combats
    if spec == "any":
        return True
    if spec in ("battlefield", "library"):
        return arrival.from_zone == spec
    if spec == "not_battlefield":
        return arrival.from_zone is not None and arrival.from_zone != "battlefield"
    if spec == "milled":
        return arrival.from_zone == "library" and any(f.kind == "mill" and f.object_id == oid for f in r.turn_log.facts)
    # discarded (701.9a: from a hand to the graveyard, recorded as a discard of this object) or put there from a library
    return arrival.from_zone == "library" or (arrival.from_zone == "hand" and any(
        f.kind == "discard" and f.object_id == oid for f in r.turn_log.facts))


def _has_counter(card: CardInstance, kind: str) -> bool:
    kind, _, need = kind.partition(">=")  # (wave 30L: "with three or more level counters on it")
    return (sum(card.counters.values()) if kind == COUNTER_ANY else card.counters.get(kind, 0)) >= int(need or 1)
# -- end counters (wave 5H) --


# -- chosen type (wave 4J) ------------------------------------------------------------------------------------------
# "creatures you control of the chosen type", "a spell of the chosen color", "creatures that aren't of the chosen
# type": the creature type (205.3m) / color (105.1) chosen for the source — as it entered ("As ~ enters, choose a
# creature type": its public "Chosen creature type" record, 614.12a), or earlier in the same resolution ("Choose a
# creature type. Destroy all creatures that aren't of the chosen type": bind_chosen substitutes that answer).
# ``matches`` reads the source's record; without a source or a valid record nothing matches (never a guess).
CHOSEN_EXTRAS = {"chosen_any_land_type": "land type", "not_chosen_any_land_type": "land type", "chosen_type": "creature type", "chosen_color": "color", "not_chosen_type": "creature type",
                 "not_chosen_color": "color", "chosen_name": "card name", "chosen_card_type": "card type", "not_chosen_card_type": "card type", "chosen_land_type": "basic land type", "not_chosen_land_type": "basic land type", "chosen_number": "number",
                 "chosen_parity_mv": "odd or even", "not_chosen_parity_mv": "odd or even", "chosen_parity_power": "odd or even", "chosen_cmp": "number"}  # (wave 50J: the quality chosen as the ability resolves)  # (wave 47A: card type, Umori; wave 49B: number, Talion)  # (-- card names (wave 22B) -- app/rules/card_names.py)


# -- extremes (wave 49C) -- 115.1: "creature with the greatest power among creatures on the battlefield" (Topple), "nonland permanent with the lowest mana value" (Culling Scales): one
# that no object of the scope beats (a tie is no beating: "target any one of them"), judged as it is chosen and again as it resolves (608.2b); the scope is the sentence's own
# ("among creatures you control") or the selector itself
@_suffix(r"with the (?P<which>greatest|lowest|least) (?P<what>power|toughness|mana value)(?: among (?P<scope>.+?))?")
def _extreme(s: Selector, m: re.Match[str]) -> Selector:
    scope = "self"
    if m["scope"]:
        if not re.search(r"(?:on the battlefield|you control|you don't control|your opponents control|an opponent controls)$", m["scope"]):
            raise ValueError(m["scope"])  # (a bare "among creatures": whose? "Each opponent chooses a creature with the greatest mana value among creatures they control" strips the owner first)
        base = _parse(m.string[: m.start()])  # (the kind is among its own kind: "a creature with the greatest power among artifacts" is no extreme of a group it isn't in)
        scope_sel = _parse(re.sub(r"s( on the battlefield| you control| you don't control| an opponent controls)?$", r"\1", m["scope"]).replace(" on the battlefield", ""))
        if scope_sel is None or scope_sel.player is not None or scope_sel.card or scope_sel.zones != ("battlefield",) \
                or base is None or (base.types, base.not_types) != (scope_sel.types, scope_sel.not_types):
            raise ValueError(m["scope"])  # (not a group of permanents of its kind: no selector)
        scope = scope_sel.key()
    return replace(s, extras=(*s.extras, f"ext:{'greatest' if m['which'] == 'greatest' else 'least'}:{ {'mana value': 'mv'}.get(m['what'], m['what']) }:{scope}"))


_SUFFIXES.insert(0, _SUFFIXES.pop())  # (before the controller suffix, whose "you control" would be taken for the whole phrase's: "… among creatures you control")


def _left_together(plan: Plan, card: CardInstance, stat: str, want: str, unwanted: str) -> list[int | None]:
    """603.10a / 700.4: a leaves-the-battlefield trigger looks back at the battlefield as it was just before the event, so
    permanents that left with this one (a board wipe, one batch) still count. Their last known information, same controller."""
    now = plan.state.cards.get(card.id)
    if now is not None and now.zone.endswith(":battlefield"):
        return []
    from app.rules.triggers import _lki_characteristics

    events = plan.rules.events

    mine = next((e for e in reversed(events) if e.card == card.id and (e.from_zone or "").endswith(":battlefield")), None)
    snap = plan.rules.lki.get(mine.object_id or "") if mine else None
    if mine is None or snap is None:
        return []
    out: list[int | None] = []
    for e in events:
        other = plan.rules.lki.get(e.object_id or "")
        if e.batch != mine.batch or e.card == card.id or other is None or not (e.from_zone or "").endswith(":battlefield") or other.controller != snap.controller:
            continue
        ch = _lki_characteristics(plan, other)
        if (not want or set(want.split("|")) & ch.types) and not set(filter(None, unwanted.split("|"))) & ch.types:
            out.append(_stat(ch, stat))
    return out


@_suffix(r"with the greatest power among creatures that player controls")  # -- extremes (wave 110I) -- Kraven the Hunter: of that object's own controller (reads greatest_own, 700.4 LKI)
def _extreme_own(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "greatest_own:power:Creature"))


_SUFFIXES.insert(0, _SUFFIXES.pop())


@_suffix(r"(?:with|that has) (?:the chosen|that) name")  # -- card names (wave 22B) -- 709.4a: one of its names is the chosen name
def _of_chosen_name(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "chosen_name"))


@_suffix(r"(?P<neg>that (?:aren't|isn't|are not|is not) )?of the chosen (?P<what>type|color)")
def _of_chosen(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, ("not_" if m["neg"] else "") + f"chosen_{m['what']}"))


@_suffix(r"with (?P<stat>mana value|power) of (?:the chosen|that) quality")  # -- chosen quality (wave 50J) -- "Choose odd or even. Destroy each creature with mana value of the chosen quality." (Thanos)
def _of_chosen_parity(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "chosen_parity_mv" if m["stat"] == "mana value" else "chosen_parity_power"))


@_suffix(r"without mana value of (?:the chosen|that) quality")
def _without_chosen_parity(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "not_chosen_parity_mv"))


@_suffix(r"with (?:an? )?(?P<q>even|odd) (?P<stat>mana values?|power)")  # -- chosen quality (wave 51C) -- "creatures with even mana values" (Void Winnower), "a permanent with an even mana value" (Desecrate Reality): 107.1, the parity test of wave 50J
def _with_parity(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, f"parity:{'mv' if m['stat'].startswith('mana') else 'power'}:{m['q']}"))


@_suffix(r"with mana value, power, or toughness equal to the chosen number")  # -- commander sweep (wave 49B) -- Talion, the Kindly Lord: any of the three equals the number chosen as it entered
def _of_chosen_number(s: Selector, m: re.Match[str]) -> Selector:
    return replace(s, extras=(*s.extras, "chosen_number"))


_CMP_OPS = {"equal to": "==", "greater than or equal to": ">=", "less than or equal to": "<=", "greater than": ">", "less than": "<"}


@_suffix(r"with (?P<what>mana value|power|toughness) (?:(?P<op>equal to|greater than or equal to|less than or equal to|greater than|less than) )?the chosen number")
def _cmp_chosen_number(s: Selector, m: re.Match[str]) -> Selector:  # -- chosen filters (wave 53B) -- "Destroy all creatures with power greater than or equal to the chosen number." (Expel the Interlopers): the number chosen as the ability resolves (bind_chosen) or as the source entered (_chosen_ok)
    what = {"mana value": "mv", "power": "power", "toughness": "toughness"}[m["what"]]
    return replace(s, extras=(*s.extras, "chosen_cmp"), compare=(*s.compare, (what, _CMP_OPS[m["op"] or "equal to"], "chosen_n")))


BASIC_LAND_TYPES_SEL = ("Plains", "Island", "Swamp", "Mountain", "Forest")


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
    if what == "number" and "chosen_cmp" in sel.extras:  # -- chosen filters (wave 53B) -- the number just chosen, in the comparison
        return replace(sel, extras=rest, compare=tuple((w, o, int(value) if n == "chosen_n" else n) for w, o, n in sel.compare)) if value.isdigit() else None
    if what == "odd or even" and value in ("Odd", "Even"):  # -- chosen quality (wave 50J) -- 107.1: zero is even
        parity = value.lower()
        if "not_chosen_parity_mv" in sel.extras:
            parity = "even" if parity == "odd" else "odd"
        return replace(sel, extras=(*rest, f"parity:{'power' if 'chosen_parity_power' in sel.extras else 'mv'}:{parity}"))
    if what == "creature type" and value in CREATURE_TYPES:
        if sel.subtypes or sel.not_subtypes or sel.union:
            return None
        if neg:
            return replace(sel, extras=rest, not_subtypes=(value,))
        return replace(sel, extras=rest, subtypes=(value,))
    if what == "land type":
        from app.rules.layers import LAND_TYPES

        if value not in LAND_TYPES or sel.subtypes or sel.not_subtypes or sel.union:
            return None
        forms = tuple(dict.fromkeys((value, value.replace("'", "’"), value.replace("’", "'"))))
        return replace(sel, extras=rest, not_subtypes=forms) if neg else replace(sel, extras=rest, subtypes=forms)
    if what == "basic land type" and value in BASIC_LAND_TYPES_SEL:  # -- chosen filters (wave 53B) -- "a land of the chosen type" (Roots of Life, Shimmer): 305.6, 205.3i
        if sel.subtypes or sel.not_subtypes or sel.union:
            return None
        return replace(sel, extras=rest, not_subtypes=(value,)) if neg else replace(sel, extras=rest, subtypes=(value,))
    if what == "card type" and value in CARD_TYPES.values():  # -- commanders (wave 47A) -- the card type chosen as the source entered (Umori, Stenn)
        if sel.types or sel.not_types:
            return None
        return replace(sel, extras=rest, not_types=(value,)) if neg else replace(sel, extras=rest, types=(value,))  # (wave 53B: "that aren't of the chosen type")
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
    label = {"land type": "Chosen land type", "creature type": "Chosen creature type", "basic land type": "Chosen basic land type", "color": "Chosen color", "card name": "Chosen card name", "card type": "Chosen card type", "number": "Chosen number", "odd or even": "Chosen quality"}[what]
    value = card.choices.get(label)
    return value.strip() if value else None


def _parity_holds(card: CardInstance | None, ch: Characteristics, mv: bool, even: bool) -> bool:
    """-- chosen quality (wave 50J) -- is its mana value (a spell's X counts on the stack, 202.3e) or power odd / even? (107.1: zero is even; a power of * is no number)"""
    from app.rules.stack_interaction import mana_value

    quality = mana_value(card, ch) if mv else (ch.pt[0] if ch.pt is not None else None)
    return quality is not None and (int(quality) % 2 == 0) == even


def _chosen_ok(plan: Plan, sel: Selector, ch: Characteristics, source: str | None, card: CardInstance | None = None) -> bool:
    what = chosen_what(sel)
    if what == "odd or even":  # the quality the source chose as it entered (Gollum, Riddle Master)
        quality = source_choice(plan, source, what)
        return quality in ("Odd", "Even") and _parity_holds(card, ch, "chosen_parity_power" not in sel.extras, (quality == "Even") != ("not_chosen_parity_mv" in sel.extras))
    if what == "number" and "chosen_cmp" in sel.extras:
        return True  # -- chosen filters (wave 53B) -- the comparison itself (matches) already read the number the source chose as it entered
    if what == "number":  # (wave 49B) a spell's mana value, power or toughness is the number the source chose as it entered (a power or toughness of * is no number here)
        from app.rules.stack_interaction import mana_value

        n = source_choice(plan, source, "number")  # (review 41: a spell's X counts on the stack, 202.3e; Talion ruling 2023-09-01)
        return n is not None and n.isdigit() and (mana_value(card, ch) == int(n) or (ch.pt is not None and int(n) in tuple(ch.pt)))
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
    if bound.types and not set(bound.types) & ch.types:  # (wave 47A: a card type)
        return False
    if set(bound.not_types) & ch.types:  # (wave 53B: "that aren't of the chosen type")
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
    if low == "stickered":
        return replace(s, extras=(*s.extras, "sticker101:any"))
    if low in ("another", "other"):
        return replace(s, other=True)
    if low in ("tapped", "untapped"):
        return replace(s, tapped=low == "tapped")
    if low == "attacking":
        return replace(s, attacking=True)
    if low == "blocking":
        return replace(s, blocking=True)
    if low == "suspended":  # -- counters (wave 41A) -- 702.62b: "each suspended card you own" (Rose Tyler): in exile, with suspend and a time counter on it
        return replace(s, zones=("exile",), extras=(*s.extras, "suspended"))
    if low == "blocked":  # -- most-played cards (wave 49A) -- 509.1h: an attacking creature that has become blocked (Smite, Warpath)
        return replace(s, attacking=True, extras=(*s.extras, "blocked"))
    if low == "unblocked":  # -- keywords (wave 15E) -- ninjutsu 702.49a: "unblocked attacking creature" (509.1h: not blocked)
        return replace(s, attacking=True, extras=(*s.extras, "unblocked"))
    if low in ("attacking-or-blocking", "blocking-or-attacking"):  # (joined by parse: one status)
        return replace(s, in_combat=True)
    if low == "tapped-or-blocking":  # -- cant restrictions (wave 50G) -- "target tapped or blocking creature" (Tetsuo Umezawa): either state, 506.4
        return replace(s, extras=(*s.extras, "tapped_or_blocking"))
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
    if low == "chosen":  # -- chosen objects (wave 110A) -- "the chosen creature": the object the source chose as it entered (wave110a_pick)
        return replace(s, extras=(*s.extras, "picked110a"))
    if low in ("enchanted", "equipped", "modified", "historic", "goaded", "renowned"):  # (wave 11C: modified 700.9, historic 700.6; wave 22E: goaded 701.15; wave 47A: renowned 702.112b)
        return replace(s, extras=(*s.extras, low))
    if low in ("face-down", "face-up"):  # -- keyword actions & face-down (wave 3F) -- 708: "face-down creatures you control"
        return replace(s, extras=(*s.extras, low.replace("-", "_")))
    if low in ("noncommander", "non-commander"):  # -- most-played cards IV (wave 51G) -- "all noncommander creatures and planeswalkers" (Slash the Ranks): any player's commander is left out (903.3)
        return replace(s, extras=(*s.extras, "not_commander"))
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
_SPELL_OR_ABILITY = re.compile(r"spell or ability|spell, activated ability, or triggered ability|instant spell, sorcery spell, activated ability, or triggered ability")


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


# -- retarget (wave 100O) -- 115.9c: "… that targets only this creature / only a single creature / only a player" (Torchling, Muck Drubb, Rebound): one
# different object or player was chosen (however many times), and it is that now (115.9b). Extra "targets_only:<self|player|selector key>".
def _targets_only_suffix(s: Selector, m: re.Match[str]) -> Selector:
    w = m["w"]
    sub = parse(w[len("a single "):]) if w.startswith("a single ") else None
    if w in ("this creature", "~", "a player"):
        key = "player" if w == "a player" else "self"
    elif sub is not None and sub.zones == ("battlefield",) and sub.player is None and not sub.extras and sub.ability is None and not sub.card:
        key = sub.key()
    else:
        raise ValueError("unread target condition")
    return replace(s, extras=(*s.extras, "targets_only:" + key))


_SUFFIXES.insert(0, (re.compile(r" that targets only (?P<w>.+)$"), _targets_only_suffix))
# -- retarget (wave 100O) -- "target spell you control that wasn't cast" (Errant, Street Artist): a spell with no cast record — a copy (707.10)
_SUFFIXES.insert(0, (re.compile(r" that wasn't cast$"), lambda s, m: replace(s, extras=(*s.extras, "not_cast"))))


def targets_only(plan: Plan, card: CardInstance, key: str, you: str, source: str | None) -> bool:
    """115.9c: the spell or ability (an Aura spell's one target too) has one different target, and it is that now; 115.9b: a player
    who left the game, or an object no longer in its zone (a new object, 400.7), is ignored."""
    from app.rules import stack_interaction  # (it imports this module)

    entry = stack_interaction.target_entry(plan, card.id) if plan.rules is not None else None
    if entry is None or len({t.id for t in entry.targets}) != 1:
        return False
    t = entry.targets[0]
    if t.id in plan.state.players:
        return key == "player" and not plan.state.players[t.id].left
    target = plan.state.cards.get(t.id)
    if key == "player" or target is None or not target.zone.endswith(":battlefield") or plan.oid(target) != t.object_id:
        return False
    return target.id == source if key == "self" else matches(plan, from_key(key), target, plan.ch(target), you, source)


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
    from app.rules import copying, stack_interaction  # (copying imports this module)

    entry = stack_interaction.target_entry(plan, card.id) if plan.rules is not None else None  # (wave 100O: an Aura spell's one target too, 115.1b)
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
    if phrase.strip() == "planeswalker that was activated this turn or tapped creature":  # -- wave 110A -- Cut Short: a different qualifier per kind;
        # "activated" = a loyalty ability of it was activated this turn (606; RulesState.loyalty_used)
        return Selector(either=(Selector(types=("Planeswalker",), extras=("loyalty_activated110a",)).key(), Selector(types=("Creature",), tapped=True).key()))
    sticker = re.fullmatch(r'(?P<base>.+?) with (?:a|an) (?P<kind>name|art|ability|power and toughness) sticker(?: on (?:it|them))?', phrase.strip())
    if sticker is not None:
        base = parse(sticker['base'])
        kind = 'pt' if sticker['kind'] == 'power and toughness' else sticker['kind']
        return replace(base, extras=(*base.extras, 'sticker101:' + kind)) if base is not None else None
    if phrase.strip() in ('double-faced card', 'double-faced cards'):
        return Selector(zones=(), card=True, extras=('double_faced_card',))
    controlled_land = re.fullmatch(r"(?P<base>.+?) whose controller controls (?:a|an) (?P<land>Plains|Island|Swamp|Mountain|Forest)",phrase.strip())
    if controlled_land is not None:
        base = parse(controlled_land['base'])
        return replace(base,extras=(*base.extras,'controller_controls_land:' + controlled_land['land'])) if base is not None else None
    # This explicit Oracle list denotes three fixed card names, including when
    # self-text normalization replaced Shield's printed name with '~'. Build
    # complete Equipment branches: outer OR constraints are not intersections.
    if phrase.strip() in ("Equipment named Sword of Kaldra, Shield of Kaldra, and Helm of Kaldra",
                          "Equipment named Sword of Kaldra, ~, and Helm of Kaldra"):
        names = ("Sword of Kaldra", "Shield of Kaldra", "Helm of Kaldra")
        return Selector(either=tuple(Selector(subtypes=("Equipment",), extras=("name:" + name,)).key() for name in names))
    suspended_union = re.fullmatch(r"(?P<permanent>(?:nonland )?permanents?(?: you control| with a time counter on (?:it|them))?) or "
                                  r"(?P<suspended>suspended cards?(?: you own)?)", phrase.strip())
    if suspended_union is not None:
        # The suspended branch stays restricted to actual suspended cards in exile (702.62b).
        branches = [_parse(suspended_union[k]) for k in ("permanent", "suspended")]
        if any(branch is None for branch in branches):
            return None
        return Selector(either=tuple(branch.key() for branch in branches if branch is not None), zones=("battlefield", "exile"))
    # A compound first branch keeps its intersection: (artifact AND creature)
    # OR Vehicle. Leading and trailing qualifiers apply to both branches.
    compound_union = re.fullmatch(
        r"(?P<pre>(?:(?:another|other) )?(?:nontoken )?)(?P<left>(?:artifact|enchantment|land) creatures?) or "
        r"(?P<right>[A-Z][A-Za-z'-]*s?)(?P<post> you control| your opponents control| you don't control)?", phrase.strip())
    if compound_union is not None:
        right_core = _core(compound_union["right"])
        if right_core is None or right_core[0] != "sub":
            return None
        branches = [_parse(_type_and(compound_union["pre"] + compound_union[k] + (compound_union["post"] or "")))
                    for k in ("left", "right")]
        if any(branch is None or branch.either or branch.player is not None for branch in branches):
            return None
        return Selector(either=tuple(branch.key() for branch in branches if branch is not None))
    # -- attached (wave 100F) -- "enchanted creature or enchantment creature [you control]" (Feast of Dreams, Nyx Herald, Karametra's Blessing): a creature with an
    # Aura attached (303.4) or one that is an enchantment, either one (each half read with the shared tail)
    either_kind = re.fullmatch(r"(?P<pre>(?:another |other )?)enchanted (?P<n>creature) or enchantment creature(?P<post> you control| you don't control)?", phrase.strip())
    if either_kind is not None:
        halves = [_parse(_type_and(f"{either_kind['pre']}{k} {either_kind['n']}{either_kind['post'] or ''}")) for k in ("enchanted", "enchantment")]
        if any(h is None or h.either or h.player is not None for h in halves):
            return None
        return Selector(either=tuple(h.key() for h in halves if h is not None))
    relative = re.fullmatch(r"(?P<base>(?:creatures?|permanents?)(?: you control| your opponents control| you don't control)?) "
                            r"that (?:are|is) (?P<traits>[A-Za-z]+(?: and/or [A-Za-z]+)+)", phrase.strip(), re.I)
    if relative is not None:
        # One union of objects, not separate effects: matching both traits does not apply a
        # continuous effect twice (613.1f, 613.4c; On Wings of Gold).
        alternatives = []
        for trait in relative["traits"].split(" and/or "):
            singular = _singular(trait)
            if singular.lower() == "token" or singular.lower() in COLORS or singular.lower() in CARD_TYPES:
                qualifier = singular.lower()
            elif singular in CREATURE_TYPES or singular in OTHER_SUBTYPES:
                qualifier = singular
            else:
                break
            branch = _parse(_type_and(qualifier + " " + relative["base"]))
            if branch is None or branch.either or branch.player is not None:
                break
            alternatives.append(branch)
        else:
            first = alternatives[0]
            return Selector(either=tuple(s.key() for s in alternatives), zones=first.zones, zone_owner=first.zone_owner, card=first.card)
    # -- layers (wave 49C) -- "white creatures and blue creatures" (Magistrate's Veto): the creatures that are white or blue, as "white or blue creatures"
    phrase = re.sub(r"^(white|blue|black|red|green) creatures and (white|blue|black|red|green) creatures$", r"\1 or \2 creatures", phrase.strip(), flags=re.I)
    # -- layers (wave 49C) -- "nonattacking creature" (Alarum), "nonattacking, nonblocking creature" (Unlikely Alliance): not attacking / not blocking (506.4)
    lead = re.match(r"^(?P<pre>(?:another |other )?)(?P<adj>nonattacking(?:,? (?:and )?nonblocking)?|nonblocking) (?P<rest>.+)$", phrase.strip())  # (wave 50F: "another nonattacking creature you control", Spider-Man, To the Rescue)
    if lead is not None:
        base = _parse(_type_and(lead["pre"] + lead["rest"]))
        flags = tuple(f for w, f in (("nonattacking", "not_attacking"), ("nonblocking", "not_blocking")) if w in lead["adj"])
        return None if base is None else replace(base, extras=(*base.extras, *flags))
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


_CLAUSE_WORDS = re.compile(r"\b(?:with|without|that|who|you|your|they|their|an opponent|opponents?|controls?|owns?|among|named|other|another|"
                           r"attached|enchanted|equipped|from|in|on|of)\b")


_TRAILING_CONTROLLER = re.compile(r"^(?P<body>.+?) (?P<clause>an opponent controls|you control|your opponents control|you don't control)$")


def _each_own_qualifier(phrase: str) -> Selector | None:
    """-- static_other sweep (wave 26A) -- "land or nonblack creature", "black creature or black planeswalker", "artifact or tapped creature",
    "Forest, green enchantment, or green planeswalker" (target phrases): a list of kinds, each with the qualifier written in front of it
    (115.1: any of them is a legal target). Read only when each kind stands on its own: no clause after a kind (a controller or "with …"
    belongs to which kind?), and no qualified first kind followed by a bare one ("tapped artifact or creature": does "tapped" carry over?)."""
    parts = [p.strip() for p in re.split(r",? or |, ", phrase) if p.strip()]
    if len(parts) < 2 or _CLAUSE_WORDS.search(phrase):
        return None
    subs = [s for s in map(_parse, parts) if s is not None]
    if len(subs) < len(parts) or any(s.player is not None or s.card or s.either or s.union or s.ability is not None
                                     or s.zones != ("battlefield",) or s.other for s in subs):
        return None
    bare = [replace(s, types=(), subtypes=()) == Selector() for s in subs]
    if not bare[0] and any(bare[1:]):
        return None
    return Selector(either=tuple(s.key() for s in subs))


_CARD_EITHER = re.compile(r"(?P<a>[A-Za-z -]+? card) or (?:an? )?(?P<b>[A-Za-z -]+? card) (?P<z>from (?:your|a) graveyard)")


_OR_OTHER = re.compile(r"(?P<a>[a-z]+) (?:and/or|or) other (?P<b>[a-z]+)")


def parse_either(phrase: str) -> Selector | None:
    """"artifact, enchantment, or creature with flying" (a target phrase: 115.1): an artifact, an enchantment, or a creature with
    flying — the qualifier is the last kind's only."""
    # -- most-played cards (wave 43B) -- "artifact, enchantment, or nonbasic land an opponent controls" (Boseiju, Who Endures): the controller clause closes the
    # whole list (115.1: each kind is a legal target for the same player's permanents), the qualifier "nonbasic" stays the last kind's own
    tail = _TRAILING_CONTROLLER.match(phrase.strip())
    if tail is not None:
        inner = parse_either(tail["body"])
        ctl = _parse("permanent " + tail["clause"])
        if inner is not None and inner.either and ctl is not None and ctl.controller is not None \
                and all(from_key(k).controller is None for k in inner.either):
            return Selector(either=tuple(replace(from_key(k), controller=ctl.controller).key() for k in inner.either))
    # -- trigger other (wave 48C) -- "legendary or Rat card from your graveyard" (Nashi, Moon's Legacy): the adjective is one kind's own, "legendary card or Rat card"
    phrase = re.sub(r"^(legendary) or ([A-Za-z ]+? card from (?:your|a) graveyard)$", r"\1 card or \2", phrase.strip())
    # -- most-played cards II (wave 45A) -- "Dragon creature card or Ugin planeswalker card from your graveyard" (Haven of the Spirit Dragon): two kinds of card, each with
    # its own qualifier, in one zone the tail names (115.1: a card of either kind is a legal target)
    z = _CARD_EITHER.fullmatch(phrase.strip())
    if z is not None:
        a, b = _parse(f"{z['a']} {z['z']}"), _parse(f"{z['b']} {z['z']}")
        if a is None or b is None or not (a.card and b.card) or a.either or b.either or a.zones != b.zones or a.zone_owner != b.zone_owner:
            return None
        return Selector(either=(a.key(), b.key()), zones=a.zones, zone_owner=a.zone_owner, card=True)
    o = _OR_OTHER.fullmatch(phrase.strip())
    if o is not None:  # -- if you do (wave 52A) -- "creature and/or other planeswalker" (Sorin, Lord of Innistrad): the "other" is the second kind's own, a creature is any creature
        a, b = _parse(o["a"]), _parse(f"other {o['b']}")
        if a is None or b is None or a.player or b.player or a.zones != ("battlefield",) or b.zones != ("battlefield",) or a.other or not b.other:
            return None
        return Selector(either=(a.key(), b.key()))
    m = _EITHER.match(phrase.strip())
    if m is None:
        return _each_own_qualifier(phrase.strip())
    a, b = _parse(m["head"] or m["head2"]), _parse(m["last"] or m["last2"])
    if a is None or b is None or a.player or b.player or a.zones != ("battlefield",) or b.zones != ("battlefield",):
        return None
    mv = tuple(c for c in b.compare if c[0] == "mv")
    if mv and not a.compare:  # -- cost reductions paid with objects (wave 47C) -- "artifact, creature, or enchantment with mana value X or less" (March of Otherworldly Light): every permanent has a
        a = replace(a, compare=mv)  # mana value, so it limits each kind (a power or a keyword belongs to the last kind alone, as for Exorcise)
    return Selector(either=(a.key(), b.key()))


# -- stack interaction (wave 23B) -- "activated ability, triggered ability, or legendary spell" (Tale's End), "triggered ability or
# colorless spell" (Consign to Memory), "activated ability, triggered ability, or noncreature spell" (Louisoix's Sacrifice): one
# object on the stack that is any of these (115.1: each kind its own selector; a spell is never an ability, 115.2b)
_ABILITY_OR_SPELL = re.compile(r"^(?P<abil>activated ability, triggered ability|activated or triggered ability|activated ability|triggered ability)"
                               r",? or (?P<spell>(?:[a-z]+ )+spell)$")


def parse_stack_union(phrase: str) -> Selector | None:
    # Oracle can list the spell categories before the ability (Spider-Sense).
    listed = re.fullmatch(r"(?P<a>[a-z]+) spell, (?P<b>[a-z]+) spell, or (?P<kind>activated|triggered) ability", phrase.strip())
    if listed is not None:
        branches = [_parse(listed[k] + " spell") for k in ("a", "b")]
        if any(s is None or s.zones != ("stack",) or s.ability or s.either or s.player for s in branches):
            return None
        ability = replace(_DEFAULT, zones=("stack",), ability=listed["kind"])
        return Selector(either=(*(s.key() for s in branches if s is not None), ability.key()), zones=("stack",))
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
    if "non-outlaw" in phrase or "nonoutlaw" in phrase:  # -- most-played cards II (wave 45A) -- 700.12a: a non-outlaw has none of the five types (Shoot the Sheriff)
        phrase = re.sub(r"\bnon-?outlaw\b", " ".join(f"non-{t}" for t in OUTLAW_TYPES.split("|")), phrase)
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
    if not qualified and (two := re.fullmatch(r"(?P<a>(?:[A-Za-z]+ )?[A-Za-z]+) card or (?:an? )?(?P<b>[A-Za-z]+) card", text.strip())) is not None \
            and all(w in CARD_TYPES or w[0].isupper() for w in (*two["a"].split(), two["b"])):  # (card types and subtypes only: "basic land card or Cave card" has a supertype that is not the Cave's)
        text = f"{two['a']} or {two['b']} card"  # -- if you do (wave 51D) -- "an artifact creature card or Vehicle card" (Szarekh): the same cards as "artifact creature or Vehicle card" (a supertype in front, "legendary or …", stays unread)
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
    alt_subs = re.fullmatch(r"(?P<subs>[A-Z][\w'’-]*(?:(?:,? or |, )[A-Z][\w'’-]*)+) (?P<rest>(?:creature|artifact|enchantment|land|planeswalker)s?(?: cards?| spells?)?)",
                            text.strip())  # (wave 15B: also "Beast or Bird creature", "Beast or Bird creature spell"; wave 30J: "Pegasus, Unicorn, or Horse creature spell")
    if alt_subs is not None:
        subs = [_core(w) for w in re.split(r",? or |, ", alt_subs["subs"])]
        base = _parse(alt_subs["rest"]) if all(c is not None and c[0] == "sub" for c in subs) else None
        if base is None or base.subtypes or base.union or len(base.types) != 1 or base.player is not None:
            return None
        return replace(s, card=base.card, zones=base.zones if s.zones == ("battlefield",) else s.zones, types=base.types,
                       subtypes=tuple(dict.fromkeys(c[1] for c in subs if c is not None)))
    # -- end recursion & tutors (wave 4M) --
    text = re.sub(r"\b(white|blue|black|red|green)(,?) and/or (?=white\b|blue\b|black\b|red\b|green\b)", r"\1\2 or ", text)  # (wave 26A: 105.1 colors, "and/or" = "or")
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
        extras = (*s.extras, "stack_spell_types:Instant|Sorcery") if text.strip().startswith("instant spell,") else s.extras
        return replace(s, zones=("stack",), ability=SPELL_OR_ABILITY, extras=extras)
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
        # (-- static_other (wave 36B) -- the serial comma: "artifacts, creatures, and lands you control" (Maraxus of Keld) lists alternatives like "…, or lands")
        left = None
        if w == "and" and i > 0:
            left = _core(words[i - 1]) or (_core(words[i - 2]) if i > 1 and words[i - 1] == "," else None)
        if w == "and" and nouns and nouns[-1][0] in ("type", "sub") and left is not None \
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
        if len(nouns) != 1 or i >= 0 or replace(s, lost_life_this_turn=False) != _DEFAULT:  # ("player from your graveyard")
            return None
        return replace(s, player="opponent" if kinds[0][1] == "opponent" else "any")
    if s.lost_life_this_turn:
        return None
    types = tuple(dict.fromkeys(v for k, v in kinds if k == "type"))
    subtypes = tuple(dict.fromkeys(v for k, v in kinds if k == "sub"))
    # (-- counters (wave 33C) -- "artifact creature and/or Vehicle" (Iron Spider): an artifact creature, or a Vehicle (an artifact too, 301.7: the
    # same as an artifact that is a creature or a Vehicle); any other mix of "and" with "or" is not read, nor one with a qualifier in front: "nontoken
    # artifact creature or Vehicle" (Canoptek Spyder) — does "nontoken" go with the Vehicle too?)
    if "or" in joins and "and" in joins and not (set(types) == {"Artifact", "Creature"} and subtypes == ("Vehicle",) and i < 0):
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
    if len(subtypes) > 1 and joins == {"and"}:  # -- lead fix (wave 48) -- "Eldrazi Scion", "Spider Hero", "Elf Warriors": side by side they narrow each other (205.3)
        s = replace(s, extras=(*s.extras, "all_subtypes"))
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
        if k + 2 < len(words) and words[k + 1] == "or" and (words[k].lower(), words[k + 2].lower()) == ("tapped", "blocking"):  # (wave 50G: Tetsuo Umezawa)
            out.append("tapped-or-blocking")
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
    if kind not in ("attack", "unblocked", "targeted"):  # (wave 23B: the object that became a target, for "other than that creature")
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
    if creature is not None and (creature.zone == "stack" or creature.zone.endswith(":hand")) and attacker is None:  # -- combat (wave 110E) -- 508.5a: a spell's controller chooses among
        return {d for c in plan.state.cards.values() if c.attacking is not None and (d := _defender(plan, c.attacking))}  # the defending players
    if creature is None or creature.attacking is None:
        return set()
    d = _defender(plan, creature.attacking)
    return {d} if d else set()


def matches_player(plan: Plan, sel: Selector, pid: str, you: str, *, source_object: str | None = None) -> bool:
    if sel.player is None or pid not in plan.live():
        return False
    if sel.player_exclude is not None and (not sel.player_exclude.startswith("player:") or pid == sel.player_exclude[7:]):
        return False
    for extra100c in sel.extras:  # -- static spells (wave 100C) -- "each player who controls a white creature" (Disorder), "target player who attacked this turn"
        if extra100c.startswith(("controls100c:", "attacked100c")):
            from app.rules import static_spell100c

            if not static_spell100c.player_extra_ok(plan, extra100c, pid, you):
                return False
    if any(x.startswith('upkeep_compare75:') for x in sel.extras):
        from app.rules import trigger_upkeep_comparison75

        if not trigger_upkeep_comparison75.matches(plan, sel, pid):
            return False
    if sel.lost_life_this_turn:
        from app.rules.history import log_for

        if log_for(plan).lost.get(pid, 0) <= 0:
            return False
    if sel.damaged_by_source_this_turn:
        from app.rules.history import log_for

        if source_object is None or not any(
            fact.kind == "damage" and fact.player == pid and fact.amount > 0 and fact.object_id == source_object
            and (fact.combat or "combat100i" not in sel.extras)  # (-- activated (wave 100I) -- "dealt combat damage by ~ this turn")
            for fact in log_for(plan).facts
        ):
            return False
    if "not_source_owner100i" in sel.extras and (  # -- activated (wave 100I) -- "target player other than ~'s owner" (108.3)
            (src := plan.state.cards.get((source_object or "").rsplit(".", 1)[0])) is None or src.owner == pid):
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
    if sel.attacking_player == 'enchanted_player':
        aura = plan.state.cards.get(source or '')
        player = aura.attached_player if aura is not None else None
        if player not in plan.live():
            return False
        sel = replace(sel, attacking_player='player:' + player)
    if sel.attacking_player is not None:
        place = card.attacking
        if place is None or place.kind != 'player' or not sel.attacking_player.startswith('player:') or place.id != sel.attacking_player[7:]:
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
    if (sel.zone_owner in ("that_player", DEFENDED) or (sel.zone_owner or "").startswith("player:")) \
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
    for extra in sel.extras:
        if extra == 'combat_pirate_player95':
            from app.rules import combat_damage95

            if not combat_damage95.pirate_player(plan, card.controller):
                return False
            continue
        if extra.startswith('exclude_successor58:') and plan.oid(card) == extra.partition(':')[2]:
            return False
        if extra == 'controlled_since_turn_start69':
            from app.rules import controller_turn_history69

            if not controller_turn_history69.continuous(plan, card):
                return False
        if extra == 'enchant_creature_exact':
            from app.rules import attachments

            if attachments.enchant_selector(ch) != 'creature':
                return False
            continue

        if extra.startswith("stack_spell_types:") and card.ability is None and not set(extra.split(":", 1)[1].split("|")) & ch.types:
            return False
    for extra in sel.extras:  # (wave 5B) "… that targets you or a creature you control"
        if extra == "random_has_targets" or extra.startswith("random_artisans_uncontested"):
            from app.rules import random_target_relations

            if not random_target_relations.matches(plan, card, extra, source):
                return False
        if extra.startswith("targets:") and (zone != "stack" or not targets_match(plan, card, extra, you, source)):
            return False
        if extra.startswith("targets_only:") and (zone != "stack" or not targets_only(plan, card, extra[len("targets_only:"):], you, source)):
            return False  # -- retarget (wave 100O) --
        if extra == "not_cast" and (zone != "stack" or card.ability is not None or (
                (rec := plan.rules.payments.get(plan.oid(card)) if plan.rules is not None else None) is not None and rec.cast_from is not None)):
            return False
    if sel.union:  # "creature or Vehicle": either the type or the subtype (-- target forms (agent T) --)
        if not ((set(sel.types) <= ch.types if "all_types" in sel.extras else set(sel.types) & ch.types) or set(sel.subtypes) & ch.subtypes):
            return False  # (wave 33C: "artifact creature or Vehicle": all the types, or the subtype)
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
    if sel.subtypes and not sel.union and not (set(sel.subtypes) <= ch.subtypes if "all_subtypes" in sel.extras else set(sel.subtypes) & ch.subtypes):
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
    if sel.controller == "active" and card.controller != plan.active:
        return False
    if sel.controller is not None and (sel.controller in (THAT_PLAYER, DEFENDED) or (  # -- damage wordings (wave 6B) --
            sel.controller.startswith("player:") and card.controller != sel.controller[7:])):
        return False
    if sel.controller == "defending" and card.controller not in defending_players(plan, source, attacker):
        return False
    if "attacking_chosen_player" in sel.extras:
        from app.rules import chosen

        player = chosen.player_of(plan, source) if source is not None else None
        if player is None or card.attacking is None or card.attacking.kind != "player" or card.attacking.id != player:
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
    if sel.owner == "defending" and card.owner not in defending_players(plan, source, attacker):  # -- defending owner (wave 110C) --
        return False
    if sel.owner == "opponent" and card.owner == you:
        return False
    if sel.owner is not None and sel.owner.startswith("player:") and card.owner != sel.owner[7:]:
        return False
    if sel.other and source is not None and card.id == source:
        return False
    if sel.tapped is not None and card.tapped != sel.tapped:
        return False
    if sel.attacking and not card.is_attacking:
        return False
    if sel.blocking and not card.is_blocking:
        return False
    if sel.in_combat and not card.is_attacking and not card.is_blocking:
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
    if any(x.startswith("any_kw:") and not set(x[7:].split(",")) & ch.keywords for x in sel.extras):  # (wave 45D)
        return False
    if "no_mana_ability" in sel.extras and any(a.kind == "mana" for a in ch.abilities):  # (wave 110C)
        return False
    if "mana_ability" in sel.extras and not any(a.kind == "mana" for a in ch.abilities):  # (wave 45D)
        return False
    if "level_up100j" in sel.extras and not any(a.kind == "activated" and re.fullmatch(r"(?:\{[^}]+\})+: Put a level counter on this creature\. Activate only as a sorcery\.", a.text)
                                                for a in ch.abilities):  # -- counters (wave 100J) -- "with level up": 702.87a, as levelers.rewrite writes it
        return False
    if "phyrexian_cost100e" in sel.extras and "/P}" not in (ch.mana_cost or ""):  # -- xdamage (wave 100E) -- "a spell with {H} in its mana cost" (Rage Extractor): a Phyrexian mana symbol of any color (107.4f)
        return False
    if "turned_up_this_turn" in sel.extras:  # (wave 110F)
        from app.rules.history import log_for

        if plan.oid(card) not in log_for(plan, False).turned_up110f:
            return False
    if "nonmana_ability" in sel.extras and not any(a.kind == "activated" for a in ch.abilities):  # (wave 110F)
        return False
    if "tap_ability" in sel.extras and not any(a.kind in ("activated", "mana") and "{T}" in (a.cost or "") for a in ch.abilities):  # (wave 52D)
        return False
    if set(sel.without_keywords) & ch.keywords:
        return False
    for what, op, n in sel.compare:
        if isinstance(n, str) and n.startswith('fight90:'):
            from app.rules import fight_receipts90

            now90 = fight_receipts90.same_mv(plan, n)
            if now90 is None:
                return False
            n = now90
        elif isinstance(n, str) and n.startswith(REVEALED_STAT):
            revealed = revealed_stat(plan, source, n[len(REVEALED_STAT):])
            if revealed is None:
                return False
            n = revealed
        elif isinstance(n, str) and n.startswith(SOURCE_STAT):  # -- reanimation (wave 10A) --
            ref_value = source_stat(plan, source, n[len(SOURCE_STAT):])
            if ref_value is None:
                return False
            n = ref_value
        elif n == "counters100j":  # -- counters (wave 100J) -- "the number of counters among permanents you control" (every kind, 122.1)
            n = sum(sum(c.counters.values()) for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.controller == you and plan.in_game(c))
        elif n == YOUR_HAND:  # (wave 51G)
            n = len(plan.state.zones.get(f"{you}:hand", []))
        elif n == "your_life100c":  # -- static spells (wave 100C) -- "power greater than or equal to your life total" (Blazing Hope)
            from app.rules import static_spell100c

            n = static_spell100c.your_life(plan, you)
        elif n == "attacked100g":  # -- zones (wave 100G) -- "the number of players you attacked this combat" (Custodi Soulcaller)
            from app.rules import zones100g

            n = zones100g.attacked(plan, you)
        elif isinstance(n, str) and n.startswith(OWN_COUNTERS):  # (wave 110I) 122.1: counters on the object, as it is when checked
            n = card.counters.get(n[len(OWN_COUNTERS):], 0)
        elif n == OWN_GRAVEYARD:  # (wave 50I) its controller's graveyard, as it is when checked (608.2b: again as the spell resolves)
            n = len(plan.state.zones.get(f"{card.controller}:graveyard", []))
        elif isinstance(n, str) and n.startswith(COUNT_STAT):  # -- control change (wave 20E) --
            n = len(candidates(plan, from_key(n[len(COUNT_STAT):]), you, source))
        elif isinstance(n, str) and n.startswith("wx:"):  # -- review 28D -- a bound read again whenever it's checked (107.3c, 608.2b)
            from app.rules import where_bound

            now = where_bound.read_live(plan, n, you, source)
            if now is None:
                return False
            n = now
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
        elif n == "chosen_n":  # -- chosen filters (wave 53B) -- the number the source chose as it entered (614.12a); none recorded: nothing matches
            got = source_choice(plan, source, "number")
            if got is None or not got.isdigit():
                return False
            n = int(got)
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
        if value is None or not isinstance(n, (int, float)) or not {"<=": value <= n, ">=": value >= n, "==": value == n, "<": value < n, ">": value > n}[op]:
            return False
    for extra in sel.extras:
        if extra.startswith('sticker101:'):
            kind = extra.split(':', 1)[1]
            if not any(kind == 'any' or p.sticker.kind == kind for p in card.stickers101):
                return False
        if extra.startswith('exchange_choices92:'):
            from app.rules import exchange_choices92

            if not exchange_choices92.matches(plan, card, ch, extra):
                return False
        if extra.startswith('controller_controls_land:') and not any(
                c.controller == card.controller and c.zone.endswith(':battlefield')
                and extra[len('controller_controls_land:'):] in plan.ch(c).subtypes
                and 'Land' in plan.ch(c).types for c in plan.state.cards.values()):
            return False
        if extra.startswith("not_oid:") and plan.oid(card) == extra[8:]:  # -- player-relative selectors (wave 53A) -- "other creatures that player controls": other than the target it follows
            return False
        if extra == "not_event" and card.id == attacker:  # (wave 23B) the event's own object (``attacker``: attacker_of)
            return False
        if extra == "nameless" and ch.name:  # (wave 53C)
            return False
        if extra == "two_colors" and len(ch.colors) != 2:  # (wave 44C)
            return False
        if extra == "not_two_colors" and len(ch.colors) == 2:  # -- trigger lines (wave 100A) --
            return False
        if extra == "attached_you" and card.attached_player != you:  # -- trigger lines (wave 100A) -- 702.5d
            return False
        if extra == "power_ne_toughness" and (_stat(ch, "power") is None or _stat(ch, "toughness") is None or _stat(ch, "power") == _stat(ch, "toughness")):
            return False  # -- trigger lines (wave 100A) -- 208.1: current values
        if extra == "attacking_same100a" and not _attacking_same100a(plan, card, source):
            return False
        if extra == "enchanted" and not _has_attached(plan, card, "Aura"):
            return False
        if extra == "equipped" and not _has_attached(plan, card, "Equipment"):
            return False
        if extra.startswith("cost_symbol:") and extra[12:] not in {x for sym in re.findall(r"\{([^}]+)\}", ch.mana_cost or "") for x in sym.split("/")}:
            return False  # (wave 44B)
        if extra == "legendary_equipped" and not any(c.attached_to == card.id and "Equipment" in plan.ch(c).subtypes and "Legendary" in plan.ch(c).supertypes
                                                     for c in plan.state.cards.values()):
            return False  # (wave 44B)
        if extra == "enchanted_by_yours" and not any(c.attached_to == card.id and "Aura" in plan.ch(c).subtypes and c.controller == you
                                                     for c in plan.state.cards.values()):
            return False  # (wave 32B)
        if extra == "enchanted_or_equipped" and not (_has_attached(plan, card, "Aura") or _has_attached(plan, card, "Equipment")):
            return False
        # -- grammar (wave 11C) -- 700.9:a counter on it, equipped, or enchanted by an Aura its own controller controls
        if extra == "modified" and not (_has_counter(card, COUNTER_ANY) or _has_attached(plan, card, "Equipment") or any(
                c.attached_to == card.id and "Aura" in plan.ch(c).subtypes and c.controller == card.controller
                for c in plan.state.cards.values())):
            return False
        if extra.startswith("ctrl_lands_le:") and sum(1 for c in plan.state.cards.values() if c.zone == f"{card.controller}:battlefield"
                                                     and "Land" in plan.ch(c).types) > int(extra[14:]):
            return False  # (wave 110D)
        if extra == "not_commander" and card.commander_key is not None:
            return False  # (wave 51G)
        if extra in _NOT_EXTRAS and matches(plan, Selector(zones=sel.zones, card=sel.card, extras=(extra[4:],)), card, ch, you, source):
            return False  # (wave 15A)
        # (700.6; set only by the look-and-distribute grammar: "a historic card from among them")
        if extra == "historic" and not ("Artifact" in ch.types or "Legendary" in ch.supertypes or "Saga" in ch.subtypes):
            return False
        if extra.startswith("ext:"):  # -- extremes (wave 49C) -- no object of the scope has more (or less) of it
            _, which, what, scope = extra.split(":", 3)
            scope_sel = replace(sel, extras=tuple(x for x in sel.extras if not x.startswith("ext:"))) if scope == "self" else from_key(scope)
            mine = _stat(ch, what)
            if scope != "self" and not matches(plan, scope_sel, card, ch, you, source):
                return False  # ("among creatures you control": it is one of them)
            peers = [v for c in candidates(plan, scope_sel, you, source) if (v := _stat(plan.ch(plan.state.cards[c]), what)) is not None]
            if mine is None or (which == "greatest" and any(v > mine for v in peers)) or (which == "least" and any(v < mine for v in peers)):
                return False
        if extra.startswith("pot:"):  # (wave 15A) power or toughness (either) at most / at least n
            op, n = ("<=", int(extra[6:])) if extra[4:6] == "<=" else (">=", int(extra[6:]))
            vals = [v for v in (_stat(ch, "power"), _stat(ch, "toughness")) if v is not None]
            if not any(v <= n if op == "<=" else v >= n for v in vals):
                return False
        if extra.startswith("in:"):  # (wave 27B) mana value / power / toughness is one of the listed numbers (on the stack: X counts, 202.3e)
            _, what, listed = extra.split(":")
            value = _stat(ch, what)
            if value is not None and what == "mv" and zone == "stack" and card.stack_info is not None and card.stack_info.x:
                value += card.stack_info.x * ch.mana_cost.count("{X}")
            if value is None or value not in {int(v) for v in listed.split(",")}:
                return False
        if extra == "basic_land_type" and not ch.subtypes & {"Plains", "Island", "Swamp", "Mountain", "Forest"}:
            return False  # (wave 20D)
        if extra.startswith("pts:"):  # -- put from hand (wave 19E) -- the power and toughness added (a * is no number: no match)
            pw, tg = _stat(ch, "power"), _stat(ch, "toughness")
            if pw is None or tg is None or not (pw + tg <= int(extra[6:]) if extra[4:6] == "<=" else pw + tg >= int(extra[6:])):
                return False
        if extra == "not_attacking" and card.is_attacking:  # (wave 35D)
            return False
        if extra == "not_blocking" and card.is_blocking:  # (wave 49C)
            return False
        if extra == "tapped_or_blocking" and not (card.tapped or card.is_blocking):  # (wave 50G)
            return False
        if extra.startswith('shares_bound_card_types:') and not (ch.types & set(extra.partition(':')[2].split(','))):
            return False
        if extra.startswith("counter:") and not _has_counter(card, extra[8:]):  # (wave 5H: any kind, "*")
            return False
        if extra.startswith("nocounter:") and _has_counter(card, extra[10:]):  # -- counters (wave 5H) --
            return False
        if extra.startswith("entered_this_turn") and not _entered_now(plan, card, you if extra.endswith("_you") else None):
            return False  # (wave 5H)
        if extra == "not_entered_this_turn" and _entered_now(plan, card, None):  # (wave 41A)
            return False
        if extra == "loyalty_activated110a" and plan.rules.loyalty_used.get(plan.rules.object_id(card.id)) != plan.state.turn.number:
            return False  # -- wave 110A -- Cut Short
        if extra == "could_produce_c":  # -- wave 110A -- 106.1: colorless mana; the card's own mana abilities (continuous effects don't add to "could produce")
            from app.rules import wave110a_grants

            if not wave110a_grants.could_produce(plan, card, ch, "C"):
                return False
        if extra == "entered_since_my_turn" and not (card.zone.endswith(":battlefield") and plan.rules.objects.get(card.id, 0) > plan.rules.turn_end_objects.get(you, 0)):
            return False  # (wave 110A)
        if extra == "ctrl_cast110a":  # -- wave 110A -- Angelic Arbiter: its controller has cast a spell this turn (601.2i)
            from app.rules import history

            if not any(n.player == card.controller for n in history.log_for(plan).casts):
                return False
        if extra == "suspended":
            from app.rules import suspend_grants

            if not suspend_grants.is_suspended(plan, card):
                return False  # (wave 41A: 702.62b)
        if extra.startswith("you_put_counters:") and not _you_put_counters_now(plan, card, you, extra[17:]):
            return False  # (wave 41A: 122.6)
        if extra.startswith("put_there:") and not _put_there_now(plan, card, extra[10:]):  # -- graveyard history (wave 36A) --
            return False
        if extra == "not_put_there_combat" and _put_there_now(plan, card, "combat"):
            return False
        if extra == "picked110a":  # (wave 110A)
            from app.rules import wave110a_pick

            if not wave110a_pick.is_picked(plan, card, source):
                return False
        if extra == "attached_source" and (source is None or card.attached_to != source):  # -- activated other (wave 34B) -- attached to the source itself
            return False
        if extra == "not_host_of_source" and (src_ := plan.state.cards.get(source or "")) is not None and src_.attached_to == card.id:  # (wave 53C)
            return False
        if extra == "host_of_source" and ((src := plan.state.cards.get(source or "")) is None or src.attached_to != card.id):
            return False  # -- attached events (wave 40B) -- 303.4b, 301.5: the permanent the source (an Aura / Equipment) is attached to ("Tap enchanted creature")
        if extra.startswith("other_attachment:"):
            kind = extra.split(":", 1)[1]
            if not any(c.id != source and c.zone.endswith(":battlefield") and c.attached_to == card.id
                       and kind in plan.ch(c).subtypes for c in plan.state.cards.values()):
                return False
        if extra.startswith(("attached_creature", "attached_permanent", "attached_land")):  # -- attached events (wave 30S) -- attached to a creature (of yours); a land (wave 100I)
            host = plan.state.cards.get(card.attached_to or "")
            if host is None or not host.zone.endswith(":battlefield") or (extra.startswith("attached_creature") and not plan.ch(host).is_creature) \
                    or (extra.startswith("attached_land") and not plan.ch(host).is_land) or (extra.endswith("_you") and host.controller != you):
                return False
        if extra.startswith("all_colors:") and not set(extra[11:]) <= set(ch.colors):  # -- both colors (wave 6D) --
            return False
        if extra.endswith("100g"):  # -- zones (wave 100G) -- "transformed permanent", "power different from its base power"
            from app.rules import zones100g

            if not zones100g.extra_ok(plan, extra, card, ch, source):
                return False
        if extra.startswith(("not_sel100c:", "loyalty100c")):  # -- static spells (wave 100C) -- "each creature that isn't all colors", "… loyalty ability of a planeswalker"
            from app.rules import static_spell100c

            if not static_spell100c.extra_ok(plan, extra, card, ch, you, source, attacker):
                return False
        if extra == "shares_color_source" and ((src := plan.state.cards.get(source or "")) is None or not plan.ch(src).colors & ch.colors):
            return False  # -- static_other sweep (wave 17C) -- conspire 702.78a: a creature that shares a color with the spell
        if extra == 'shares_color_legendary_creature_you_control' and not any(
                c.controller == you and c.zone.endswith(':battlefield') and plan.in_game(c)
                and (other := plan.ch(c)).is_creature and 'Legendary' in other.supertypes and bool(other.colors & ch.colors)
                for c in plan.state.cards.values()):
            return False
        if extra.startswith("oid:") and plan.oid(card) != extra[4:]:  # (wave 18F) the granting object
            return False
        if extra == "shares_commander_type" and not _shares_commander_type_now(plan, ch, you):  # (wave 22E)
            return False
        if extra == "suspected" and not (plan.rules is not None and plan.oid(card) in plan.rules.suspected):
            return False  # -- trigger lines (wave 100A) -- 701.60a: the designation is on this object (400.7)
        if extra == "renowned" and not (plan.rules is not None and plan.oid(card) in plan.rules.renowned):
            return False  # -- commanders (wave 47A) -- 702.112b: the designation is on this object (a new object has none, 400.7)
        if extra == "goaded":  # (wave 22E) 701.15b: goaded by someone (a goad effect lasts until that player's next turn: layers' imposed rules)
            from app.rules.keyword_actions import goaded_by

            if not goaded_by(ch):
                return False
        if extra.startswith("parity:") and not _parity_holds(card, ch, extra.split(":")[1] == "mv", extra.endswith(":even")):
            return False  # -- chosen quality (wave 50J) -- the mana value (a spell's X counts on the stack, 202.3e) or power is odd / even as chosen earlier in this resolution
        if extra == "foreign_not_basic_land" and {'Basic'} <= ch.supertypes and 'Land' in ch.types:
            return False
        if extra == 'has_foretell':
            from app.rules.contextual_mana_outcomes import has_foretell
            if not has_foretell(ch):
                return False
        if extra == "has_flashback" and not any(re.match(r"flashback\b", a.text, re.IGNORECASE) for a in ch.abilities):
            return False
        if extra.startswith("name:"):  # -- card names (wave 22B) -- 709.4a, a name chosen earlier in this resolution
            from app.rules import card_names, static_perm100d  # (wave 100D: Pardic Firecat)

            if not card_names.has_name(ch, extra[5:]) and not static_perm100d.counted_as(plan, source, card, ch):
                return False
        if extra.startswith("not_name:"):
            from app.rules import card_names

            if card_names.has_name(ch, extra[9:]):
                return False
        if extra.startswith('paid_contributor81:'):
            from app.rules import crew_saddle

            _, kind, original_source = extra.split(':', 2)
            if not crew_saddle.tapped_for(plan, kind, plan.oid(card), original_source):
                return False
        if extra in ("crewed_it", "saddled_it"):  # (wave 23D)
            from app.rules import crew_saddle

            src = plan.state.cards.get(source or "")
            if src is None or not crew_saddle.tapped_for(plan, "crew" if extra == "crewed_it" else "saddle", plan.oid(card), plan.oid(src)):
                return False
        if extra.startswith("counter_cast:"):
            from app.rules import conditional_counters

            if not conditional_counters.cast_filter(plan, card, extra.split(":", 1)[1]):
                return False
        if extra == "not_cast_from_owner_hand":
            rec = plan.rules.payments.get(plan.oid(card))
            # 400.3: a card in a hand is necessarily in its owner's hand,
            # even if another player has permission to cast it from there.
            # A copied spell was not cast (707.10), so it satisfies this filter.
            if rec is not None and rec.cast_from == "hand":
                return False
        if extra == "convoked_it":  # (wave 26D)
            rec = plan.rules.payments.get(plan.oid(source)) if source in plan.state.cards else None
            if rec is None or not any(c.kind == "convoke" and c.object_id == plan.oid(card) for c in rec.contributions):
                return False
        if extra == "named_self" and ((src := plan.state.cards.get(source or "")) is None or plan.ch(src).name != ch.name):
            return False  # (wave 12C)
        if extra == "not_named_self" and ((src := plan.state.cards.get(source or "")) is None or plan.ch(src).name == ch.name):
            return False  # (wave 47D)
        if extra.startswith(("samename", "nosamename")) and not _same_name_now(plan, extra, card, ch, you, source):
            return False  # (wave 32A)
        if extra == "attacking_alone" and sum(1 for c in plan.state.cards.values() if c.is_attacking and c.zone.endswith(":battlefield")) != 1:
            return False  # -- activated other (wave 42C) -- 506.5 (the same count statics.py reads for "as long as it's attacking alone")
        if extra == "attacking_you" and (card.attacking is None or card.attacking.kind != "player" or card.attacking.id != you):
            return False
        if extra == "attacking_battle" and (card.attacking is None or card.attacking.kind != "card" or (attacked := plan.state.cards.get(card.attacking.id)) is None
                                            or "Battle" not in plan.ch(attacked).types):  # (wave 100K)
            return False
        if extra == "attacking_you_pw" and (card.attacking is None or not (  # -- most-played cards III (wave 46C) -- 506.3: attacks you, or a planeswalker you control
                (card.attacking.kind == "player" and card.attacking.id == you) or (card.attacking.kind == "card" and (target_walker := plan.state.cards.get(card.attacking.id)) is not None
                                                                                   and "Planeswalker" in plan.ch(target_walker).types and target_walker.controller == you))):
            return False
        if extra == "attacking_opponent_pw":
            target = card.attacking
            if target is None:
                return False
            if target.kind == "player":
                defender = target.id
            else:
                walker = plan.state.cards.get(target.id)
                if walker is None or not walker.zone.endswith(":battlefield") or "Planeswalker" not in plan.ch(walker).types:
                    return False
                defender = walker.controller
            if defender == you or defender not in plan.live():
                return False
        if extra == "attacking_opponent" and (card.attacking is None or card.attacking.kind != "player" or card.attacking.id == you
                                              or card.attacking.id not in plan.live()):
            return False  # (wave 45A)
        if extra in ("face_down", "face_up") and card.face_down != (extra == "face_down"):  # -- wave 3F --
            return False
        if extra == "morph_ability" and not {"morph", "megamorph"} & ch.keywords:
            return False
        if extra == "cycling_ability" and not any(k.endswith("cycling") for k in ch.keywords):  # (wave 20C)
            return False
        if extra == "kicker_ability" and not {"kicker", "multikicker"} & ch.keywords:  # (wave 43D)
            return False
        if extra == "blocked" and card.id not in plan.rules.blocked:  # (wave 49A)
            return False
        if extra == "unblocked" and (card.id in plan.rules.blocked or not _blockers_declared(plan)):  # (wave 15E) a blocked attacker stays blocked; (wave 53C) 509.1h: it is unblocked once blockers are declared
            return False
        if extra == "attacked_you_this_turn" and (plan.state.rules is None or plan.state.rules.turn_log.turn != plan.state.turn.number
                                                  or you not in plan.state.rules.turn_log.attacked_who.get(plan.state.rules.object_id(card.id), [])):  # (wave 110F)
            return False
        if extra == "attacked_this_turn" and not _attacked_this_turn_now(plan, card):  # -- combat (wave 5C) --
            return False
        if extra == "didnt_attack_this_turn" and _attacked_this_turn_now(plan, card):  # -- damage sized by a count (wave 34D) --
            return False
        if extra == "protected_by_opp110g" and __import__("app.rules.battles", fromlist=["x"]).protector(plan.state, card) in (None, you):  # -- (wave 110G) -- 310.8: a battle an opponent protects
            return False
        if extra == "didnt_attack_combat110g" and card.is_attacking:  # -- (wave 110G) -- 508.1: not among this combat's declared attackers (Total War)
            return False
        if extra == "blocked_this_turn" and not _blocked_this_turn_now(plan, card):  # -- combat state (wave 27A) --
            return False
        if extra == "attacked_or_blocked_this_turn" and not (_attacked_this_turn_now(plan, card) or _blocked_this_turn_now(plan, card)):  # (wave 100K)
            return False
        if extra in ("block_involved_this_turn", "blocked_by_source_this_turn") and not _block_history(plan, card, extra, source):  # -- wave 31D --
            return False
        if extra == "last_drawn_this_turn107" and not last_drawn_now107(plan, card):
            return False
        if extra == "drawn_this_turn" and not drawn_now(plan, card):  # -- drawn this turn (wave 18G) --
            return False
        if extra in ("was_dealt_damage", "dealt_damage", "dealt_damage_you", "dealt_damage_by_source", "dealt_combat_damage_you"):  # -- damage history (wave 6B) --
            from app.rules import damage_history

            if not damage_history.matches(plan, card, extra, you, source):
                return False
        if extra in ("blocking_source", "blocked_by_source", "block_pair_this", "blocked_by_this"):  # -- damage wordings (wave 6B) -- the source's block now
            src = plan.state.cards.get(source or "")
            if src is not None and not src.zone.endswith(":battlefield") and extra in ("blocking_source", "blocked_by_source"):
                # -- activated other (wave 52D) -- 608.2b: the source left (sacrificed as a cost: Tinder Wall, Wall of Corpses, Urborg Panther) - its last known information says
                # whom it was blocking; whoever blocks it still blocks the attacker that left the battlefield (506.4, 509.1h: a blocker stays blocking)
                if not card.zone.endswith(":battlefield"):
                    return False
                last = plan.rules.last_known(src.id)
                if (not card.blocks(src.id)) if extra == "blocking_source" else (last is None or card.id not in last.blocking_ids):
                    return False
            elif src is None or not src.zone.endswith(":battlefield") or not card.zone.endswith(":battlefield") or ((not card.blocks(src.id)) if extra == "blocking_source" else (not src.blocks(card.id)) if extra in ("blocked_by_source", "blocked_by_this") \
                    else not (card.blocks(src.id) or src.blocks(card.id))):
                return False
        if extra.startswith("rel:"):  # -- block events (wave 53C) -- combat and attachment relations to a named creature (app/rules/block_events.py)
            from app.rules import block_events

            if not block_events.rel_matches(plan, card, extra, source):
                return False
        if extra in ("shares_type_source", "shares_type_event"):  # -- most-played cards (wave 43B) -- a creature type in common with the object ``source`` names (205.3m)
            from app.rules.creature_types import CREATURE_TYPES

            src = plan.state.cards.get(source or "")
            # ponytail: the source's current characteristics, not last-known information (no subtypes are stored in the LKI snapshot)
            if src is None or not (ch.subtypes & plan.ch(src).subtypes & CREATURE_TYPES):
                return False
        if extra in ("shares_color_host110a", "shares_type_host110a"):  # -- wave 110A -- 105.2 / 205.3m: in common with the creature the source is attached to
            from app.rules.creature_types import CREATURE_TYPES

            src = plan.state.cards.get(source or "")
            host = plan.state.cards.get(src.attached_to or "") if src is not None else None
            if host is None or not ((ch.colors & plan.ch(host).colors) if extra == "shares_color_host110a"
                                    else (ch.subtypes & plan.ch(host).subtypes & CREATURE_TYPES)):
                return False
        if extra == 'double_faced_permanent66':
            from app.rules import tetzin_double_face66

            if not tetzin_double_face66.physical(plan, card):
                return False
        if extra == 'double_faced_card':
            from app.cards.repository import DOUBLE_FACED_LAYOUTS

            data = plan.info.get(card.card_id) if card.card_id else None
            # CR 712.1 includes meld cards. Image availability is not a card characteristic.
            if card.face_down or not data or data.get('layout') not in DOUBLE_FACED_LAYOUTS:
                return False
        if extra == "has_adventure":  # (wave 25B) the printing is an adventurer card, whichever half it is as it is cast
            data = plan.info.get(card.card_id) if card.card_id else None
            faces = (data or {}).get("faces") or []  # (review 25B: an omen card shares the layout but has an Omen, 720.2a, not an Adventure)
            if card.face_down or not (data and data.get("layout") == "adventure" and len(faces) > 1 and "Adventure" in str(faces[1].get("type_line") or "")):
                return False  # (-- review 34 -- 406.3a, 708.2: a face-down card has no characteristics: its printing is nobody's business, Howling Galefang)
        if extra == "greatest_power_own":  # -- damage wordings (wave 6B) -- the greatest power among creatures its
            # controller controls (Crackling Doom: what the sacrificing player may choose; ties all qualify)
            mine = _stat(ch, "power")
            others = [_stat(plan.ch(c), "power") for c in plan.state.cards.values()
                      if c.controller == card.controller and c.zone.endswith(":battlefield") and plan.ch(c).is_creature]
            if mine is None or any(p is None or p > mine for p in others):
                return False
        if extra.startswith(("greatest_own:", "least_own:")):  # -- static_other sweep (wave 26A) -- "with the greatest mana value among creatures and
            # planeswalkers they control" (Blot Out): no permanent of those kinds its controller controls beats it (ties all qualify)
            # (-- trigger other (wave 39A) -- "with the least power among creatures they control": Witch-king, Bringer of Ruin; none has less)
            _, stat, kinds = extra.split(":", 2)
            stat = "mv" if stat == "mana_value" else stat
            want, _, unwanted = kinds.partition("!")
            mine = _stat(ch, stat)
            rivals = [_stat(plan.ch(c), stat) for c in plan.state.cards.values()
                      if c.controller == card.controller and c.zone.endswith(":battlefield") and plan.in_game(c)
                      and (not want or set(want.split("|")) & plan.ch(c).types) and not set(filter(None, unwanted.split("|"))) & plan.ch(c).types]
            rivals += _left_together(plan, card, stat, want, unwanted)  # -- extremes (wave 110I) -- 603.10a: creatures that left in the same event
            if mine is None or any(p is not None and (p < mine if extra.startswith("least") else p > mine) for p in rivals):
                return False
        if (extra == "no_abilities" and ch.has_abilities) or (extra == "has_abilities" and not ch.has_abilities):  # (wave 42A)
            return False
        if extra.startswith("cost_is:") and ch.mana_cost not in extra[8:].split("|"):  # (wave 51B)
            return False
        if extra == "x_cost" and "{X}" not in ch.mana_cost:  # -- activated wordings (wave 15D) -- (107.3: printed in its mana cost)
            return False
        if extra.startswith("base_pt_either:"):
            _, op, raw = extra.split(":")
            n = int(raw)
            if ch.base_pt is None or not any(v <= n if op == "<=" else v == n for v in ch.base_pt):
                return False
        if extra == "power_gt_base" and (ch.base_pt is None or (_stat(ch, "power") or 0) <= ch.base_pt[0]):  # (wave 30J) as it is now, a * is no number
            return False
        if extra == "power_eq_toughness":  # CR 208.1: current derived values, not printed/base stats or damage.
            p, t = _stat(ch, "power"), _stat(ch, "toughness")
            if p is None or t is None or p != t:
                return False
        if extra == "toughness_gt_power":  # -- damage wordings (wave 6B) -- as it is now (611.3a for a static)
            p, t = _stat(ch, "power"), _stat(ch, "toughness")
            if p is None or t is None or t <= p:
                return False
        if extra.startswith("subtype_any:") and not (set(extra[12:].split("|")) & (ch.subtypes | ch.types) or (card.is_token and "token" in extra[12:].split("|"))):  # (wave 6C; 33C: "a token or a Rabbit")
            return False
        if extra == "mergeable":  # -- merged permanents (wave 18D) -- a permanent a mutating spell can merge with (app/rules/merged.py)
            from app.rules import merged

            if not merged.mergeable(plan, card):
                return False
    # -- chosen type (wave 4J) --
    return not any(e in CHOSEN_EXTRAS for e in sel.extras) or _chosen_ok(plan, sel, ch, source, card)


def drawn_now(plan: Plan, card: CardInstance) -> bool:
    """-- drawn this turn (wave 18G) -- the card is still the object (400.7) its owner drew this turn, in their hand (PRIVATE: only
    ever read for the owner's own choices, never shown to another player)."""
    r = plan.state.rules
    if r is None or r.turn_log.turn != plan.state.turn.number or not card.zone.endswith(":hand"):
        return False
    return r.object_id(card.id) in r.turn_log.drawn.get(card.owner, ())


def last_drawn_now107(plan: Plan, card: CardInstance) -> bool:
    """The last actual hand object drawn, without falling back to an earlier survivor."""
    if not drawn_now(plan, card):
        return False
    rules = plan.state.rules
    return rules is not None and rules.turn_log.drawn[card.owner][-1] == rules.object_id(card.id)


def _you_put_counters_now(plan: Plan, card: CardInstance, you: str | None, kind: str) -> bool:
    """-- counters (wave 41A) -- ``you`` put one or more ``kind`` counters on this object (400.7) this turn (the turn's log, 608.2i)."""
    from app.rules.history import log_for

    oid = plan.oid(card)
    return any(f.kind == "counters" and f.object_id == oid and f.actor == you and f.counter == kind and f.amount > 0 for f in log_for(plan, False).facts)


def _attacked_this_turn_now(plan: Plan, card: CardInstance) -> bool:
    """-- combat (wave 5C) -- the object (400.7: not a new one) was declared as an attacker this turn (wave 4D log)."""
    r = plan.state.rules
    if r is None or r.turn_log.turn != plan.state.turn.number:
        return False
    return r.object_id(card.id) in {a for ids in r.turn_log.attackers.values() for a in ids}


def _blockers_declared(plan: Plan) -> bool:
    from app.rules import block_events

    return block_events.blockers_declared(plan)


def _blocked_this_turn_now(plan: Plan, card: CardInstance) -> bool:
    """-- combat state (wave 27A) -- the object (400.7) was declared as a blocker this turn (TurnLog.blockers)."""
    r = plan.state.rules
    return r is not None and r.turn_log.turn == plan.state.turn.number and r.object_id(card.id) in r.turn_log.blockers


def _block_history(plan: Plan, card: CardInstance, extra: str, source: str | None) -> bool:
    """-- combat history (wave 31D) -- this object (400.7) blocked or was blocked this turn / was blocked by the source (TurnLog.blocks, 509.1g)."""
    r = plan.state.rules
    if r is None or r.turn_log.turn != plan.state.turn.number:
        return False
    me = r.object_id(card.id)
    log = r.turn_log
    if extra == "block_involved_this_turn":
        return me in log.blockers or any(me in attackers for attackers in log.blocks.values())
    # (by the source as it blocked: the card is what the delayed trigger remembers — it may be dead by then, "destroy it and all creatures it blocked")
    return any(blocker.rsplit(".", 1)[0] == source and me in attackers for blocker, attackers in log.blocks.items())


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
    if what == 'color_count':
        return len(ch.colors)
    if what == "mv":
        return int(ch.mana_value)
    if what.startswith("base_"):  # (wave 30J) none known (a * or a card not on the battlefield): no number
        return None if ch.base_pt is None else ch.base_pt[0 if what == "base_power" else 1]
    if ch.pt is not None:
        return ch.pt[0] if what == "power" else ch.pt[1]
    raw = ch.power if what == "power" else ch.toughness
    return int(raw) if raw is not None and raw.lstrip("-").isdigit() else None


def _has_attached(plan: Plan, card: CardInstance, subtype: str) -> bool:
    if any(c.attached_to == card.id and subtype in plan.ch(c).subtypes for c in plan.state.cards.values()):
        return True
    # -- attached (wave 100F) -- 603.10a: ``card`` is a departed permanent as it last existed (triggers._snapshot_card; "Whenever an enchanted creature
    # dies", Hateful Eidolon) and its Auras are in the graveyard since (704.5m): read what was attached to it then (its latest departure snapshot)
    live = plan.state.cards.get(card.id)
    if live is None or live is card or live.zone == card.zone:
        return False
    from app.rules import attached100f

    snap = next((s for s in reversed(plan.rules.lki.values()) if s.card == card.id and s.zone == card.zone and s.attached_objects_known), None)
    return any(subtype in ch.subtypes for _, ch in attached100f.was_attached(plan, snap))


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


# -- block events (wave 53C) -- the suffixes "blocking that creature", "that blocked or was blocked by it this turn", "attached to target creature"
from app.rules import block_events as _block_events  # noqa: E402  (a leaf module over this one)

_block_events.register()
