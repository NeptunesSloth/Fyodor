"""Declarative ability definitions from Oracle text: the template library.

A card ability the engine automates is described as **data**: a trigger (or spell / activated /
replacement), an optional target, and a list of effects built from the primitives in
``app.rules.effects``. Common Oracle wordings map onto templates here, so one tested mechanic
unlocks every card that uses it. Nothing is ever evaluated or executed from card text; a line
either matches a known template completely or it stays manual.

Definition shape (JSON-able)::

    {"kind": "triggered" | "spell" | "activated" | "replacement",
     "trigger": "enters_self" | "dies_self" | "ltb_self" | "upkeep_you" | "end_step_you" | "attacks_self",
     "optional": bool,                       # "you may …": asked on resolution (603.5)
     "target": {"what": "creature" | "any" | …} or None,
     "cost": "{2}" (activated only),
     "effects": [{"do": "draw", "who": "you", "n": 1}, …],
     "replacement": "enters_tapped"}

Every template is covered by ``tests/test_rules_scripts.py`` (parsing) and the scenario tests
(outcomes). Hand-written scripts (``app.rules.cards``) take precedence.
"""

from __future__ import annotations

import re
from dataclasses import replace
from functools import lru_cache
from typing import Any

from app.rules.characteristics import Characteristics
from app.rules.costs import parse_ability_cost
from app.rules.oracle import AbilityText

Definition = dict[str, Any]

NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
           "nine": 9, "ten": 10}
_N = r"(?P<{name}>\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten)"
GRANTABLE = ("flying", "first strike", "double strike", "deathtouch", "lifelink", "vigilance", "trample", "haste",
             "reach", "menace", "indestructible", "hexproof")

# Target selectors (CR 115) in Oracle wording → selector key (see app.rules.targets.SELECTORS).
SELECTORS = {
    "any target": "any",
    "target creature": "creature",
    "target creature you control": "creature_you_control",
    "target creature an opponent controls": "creature_opponent_controls",
    "target creature you don't control": "creature_opponent_controls",
    "target creature or planeswalker": "creature_or_planeswalker",
    "target artifact": "artifact",
    "target enchantment": "enchantment",
    "target artifact or enchantment": "artifact_or_enchantment",
    "target land": "land",
    "target planeswalker": "planeswalker",
    "target permanent": "permanent",
    "target nonland permanent": "nonland_permanent",
    "target player": "player",
    "target opponent": "opponent",
}
_SEL = "|".join(sorted((re.escape(k) for k in SELECTORS), key=len, reverse=True))

TRIGGERS = [
    (re.compile(r"^When ~ enters, (?P<body>.+)$"), "enters_self"),
    (re.compile(r"^When ~ dies, (?P<body>.+)$"), "dies_self"),
    (re.compile(r"^When ~ leaves the battlefield, (?P<body>.+)$"), "ltb_self"),
    (re.compile(r"^At the beginning of your upkeep, (?P<body>.+)$"), "upkeep_you"),
    (re.compile(r"^At the beginning of your end step, (?P<body>.+)$"), "end_step_you"),
    (re.compile(r"^Whenever ~ attacks, (?P<body>.+)$"), "attacks_self"),
    (re.compile(r"^Whenever (?P<filter>another creature you control|a creature you control|another nontoken creature you control|"
                r"a nontoken creature you control|another creature|a creature) enters, (?P<body>.+)$"), "enters_other"),
    (re.compile(r"^Whenever you cast (?P<filter>a spell|a creature spell|a noncreature spell|an instant or sorcery spell|"
                r"an artifact spell|an enchantment spell), (?P<body>.+)$"), "cast_you"),
]


def num(word: str) -> int:
    return int(word) if word.isdigit() else NUMBERS[word.lower()]


def _signed(p: str) -> int:
    return -int(p[1:]) if p[0] in "-−" else int(p.lstrip("+"))


def self_text(text: str, name: str) -> str:
    """The ability with the card's own name (and "this creature" etc.) written as ~."""
    out = text
    for n in sorted({name, name.split(",")[0].strip()}, key=len, reverse=True):
        if len(n) >= 3:
            out = re.sub(rf"\b{re.escape(n)}\b", "~", out)
    return re.sub(r"\b[Tt]his (creature|artifact|enchantment|land|permanent|Equipment|Vehicle)\b", "~", out)


EFFECTS: list[tuple[re.Pattern[str], Any]] = []


def effect(pattern: str):  # type: ignore[no-untyped-def]
    def register(fn):  # type: ignore[no-untyped-def]
        EFFECTS.append((re.compile("^" + pattern.format(N=_N.format(name="n"), M=_N.format(name="m"), SEL=_SEL) + "$"), fn))
        return fn
    return register


@effect(r"draw {N} cards?")
def _draw(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "draw", "who": "you", "n": num(m["n"])}], None


@effect(r"target player draws {N} cards?")
def _target_draws(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "draw", "who": "target", "n": num(m["n"])}], "player"


@effect(r"each player draws {N} cards?")
def _each_draws(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "draw", "who": "each_player", "n": num(m["n"])}], None


@effect(r"you gain {N} life")
def _gain(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "gain_life", "who": "you", "n": num(m["n"])}], None


@effect(r"each opponent loses {N} life")
def _drain(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "lose_life", "who": "each_opponent", "n": num(m["n"])}], None


@effect(r"each opponent loses {N} life and you gain {M} life")
def _drain_gain(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "lose_life", "who": "each_opponent", "n": num(m["n"])}, {"do": "gain_life", "who": "you", "n": num(m["m"])}], None


@effect(r"target player loses {N} life")
def _target_loses(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "lose_life", "who": "target", "n": num(m["n"])}], "player"


@effect(r"(?:~|it) deals {N} damage to (?P<sel>{SEL})")
def _damage(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "damage", "who": "target", "n": num(m["n"])}], SELECTORS[m["sel"]]


@effect(r"~ deals {N} damage to each opponent")
def _damage_opponents(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "damage", "who": "each_opponent", "n": num(m["n"])}], None


@effect(r"~ deals {N} damage to each creature")
def _damage_creatures(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "damage", "who": "each_creature", "n": num(m["n"])}], None


@effect(r"(?P<sel>target creature|target creature you control) gets (?P<p>[+−-]\d+)/(?P<t>[+−-]\d+) until end of turn")
def _pump_target(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "pump", "who": "target", "p": _signed(m["p"]), "t": _signed(m["t"])}], SELECTORS[m["sel"]]


@effect(r"(?:~|it) gets (?P<p>[+−-]\d+)/(?P<t>[+−-]\d+) until end of turn")
def _pump_self(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "pump", "who": "self", "p": _signed(m["p"]), "t": _signed(m["t"])}], None


@effect(r"creatures you control get (?P<p>[+−-]\d+)/(?P<t>[+−-]\d+) until end of turn")
def _pump_team(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "pump", "who": "creatures_you_control", "p": _signed(m["p"]), "t": _signed(m["t"])}], None


_KW = "|".join(GRANTABLE)


@effect(rf"(?P<who>target creature|~|it) gains (?P<kw>{_KW}) until end of turn")
def _grant(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    who = "target" if m["who"].startswith("target") else "self"
    return [{"do": "grant", "who": who, "keywords": [m["kw"]]}], "creature" if who == "target" else None


@effect(rf"(?P<sel>target creature|target creature you control) gets (?P<p>[+−-]\d+)/(?P<t>[+−-]\d+) and gains (?P<kw>{_KW}) until end of turn")
def _pump_grant(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "pump", "who": "target", "p": _signed(m["p"]), "t": _signed(m["t"])},
            {"do": "grant", "who": "target", "keywords": [m["kw"]]}], SELECTORS[m["sel"]]


@effect(r"destroy (?P<sel>{SEL})")
def _destroy(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "destroy", "who": "target"}], SELECTORS[m["sel"]]


@effect(r"exile (?P<sel>{SEL})")
def _exile(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "exile", "who": "target"}], SELECTORS[m["sel"]]


@effect(r"return (?P<sel>{SEL}) to its owner's hand")
def _bounce(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "bounce", "who": "target"}], SELECTORS[m["sel"]]


@effect(r"(?P<verb>tap|untap) (?P<sel>{SEL})")
def _tap(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": m["verb"], "who": "target"}], SELECTORS[m["sel"]]


@effect(r"(?P<verb>scry|surveil) {N}")
def _scry(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": m["verb"], "who": "you", "n": num(m["n"])}], None


@effect(r"you get (?P<e>(?:\{{E\}})+)")
def _energy(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "player_counter", "who": "you", "counter": "energy", "n": m["e"].count("{E}")}], None


# Predefined tokens (CR 111.10), created with their full rules text.
PREDEFINED_TOKENS = {
    "Treasure": ("Token Artifact — Treasure", "{T}, Sacrifice this token: Add one mana of any color."),
    "Food": ("Token Artifact — Food", "{2}, {T}, Sacrifice this token: You gain 3 life."),
    "Gold": ("Token Artifact — Gold", "Sacrifice this token: Add one mana of any color."),
    "Clue": ("Token Artifact — Clue", "{2}, Sacrifice this token: Draw a card."),
    "Blood": ("Token Artifact — Blood", "{1}, {T}, Discard a card, Sacrifice this token: Draw a card."),
    "Shard": ("Token Enchantment — Shard", "{2}, Sacrifice this token: Scry 1, then draw a card."),
    "Powerstone": ("Token Artifact — Powerstone", "{T}: Add {C}. This mana can't be spent to cast a nonartifact spell."),
    "Heartwood": ("Token Artifact — Heartwood", "{T}: Add {R} or {G}."),
}
COLOR_WORDS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_COLORS_RE = r"(?P<colors>colorless|(?:white|blue|black|red|green)(?:(?:,)? (?:and )?(?:white|blue|black|red|green))*)"


@effect(r"create {N} (?P<pt>\d+/\d+) " + _COLORS_RE + r" (?P<sub>[A-Z][A-Za-z' ]*?) (?P<art>artifact )?creature tokens?(?: with (?P<kws>[a-z ,]+?))?")
def _create_creature(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    p, t = m["pt"].split("/")
    colors = [] if m["colors"] == "colorless" else [COLOR_WORDS[w] for w in re.findall(r"white|blue|black|red|green", m["colors"])]
    kws = [k.strip() for k in re.split(r", and |, | and ", m["kws"] or "") if k.strip()]
    if any(k not in GRANTABLE and k not in ("defender",) for k in kws):
        raise _NoMatch
    type_line = f"Token {'Artifact ' if m['art'] else ''}Creature — {m['sub']}"
    text = "\n".join(k.capitalize() for k in kws)
    return [{"do": "create_token", "who": "you", "n": num(m["n"]),
             "token": {"name": m["sub"], "power": p, "toughness": t, "colors": colors, "type_line": type_line, "text": text}}], None


@effect(r"create {N} (?P<kind>Treasure|Food|Gold|Clue|Blood|Shard|Powerstone|Heartwood) tokens?")
def _create_predefined(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    type_line, text = PREDEFINED_TOKENS[m["kind"]]
    return [{"do": "create_token", "who": "you", "n": num(m["n"]),
             "token": {"name": m["kind"], "power": None, "toughness": None, "colors": [], "type_line": type_line, "text": text}}], None


@effect(r"put {N} (?P<kind>\+1/\+1|-1/-1) counters? on (?P<who>target creature you control|target creature|~|it|each creature you control)")
def _counters(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    who = {"~": "self", "it": "self", "each creature you control": "creatures_you_control"}.get(m["who"], "target")
    return [{"do": "add_counters", "who": who, "kind": m["kind"], "n": num(m["n"])}], SELECTORS.get(m["who"])


@effect(r"proliferate")
def _proliferate(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "proliferate", "who": "you"}], None


WIPES = {"creatures": ["Creature"], "artifacts": ["Artifact"], "enchantments": ["Enchantment"],
         "artifacts and enchantments": ["Artifact", "Enchantment"], "creatures and planeswalkers": ["Creature", "Planeswalker"],
         "nonland permanents": ["*nonland"], "artifacts, creatures, and enchantments": ["Artifact", "Creature", "Enchantment"]}


@effect(r"destroy all (?P<what>creatures|artifacts|enchantments|artifacts and enchantments|creatures and planeswalkers|nonland permanents|artifacts, creatures, and enchantments)")
def _wipe(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "destroy_all", "who": "all", "types": WIPES[m["what"]]}], None


@effect(r"exile (?P<sel>target creature you control|target creature), then return (?:it|that card) to the battlefield under (?P<under>its owner's|your) control")
def _blink(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "blink", "who": "target", "under": "you" if m["under"] == "your" else "owner"}], SELECTORS[m["sel"]]


@effect(r"(?:it|they) can't be regenerated")
def _no_regeneration(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [], None  # the engine never regenerates (regeneration isn't automated), so this changes nothing


SEARCH_FILTERS = {"basic land card": "basic_land", "land card": "land", "creature card": "creature", "card": "any",
                  "artifact card": "artifact", "enchantment card": "enchantment", "instant or sorcery card": "instant_or_sorcery"}


@effect(r"search your library for an? (?P<what>basic land card|land card|creature card|artifact card|enchantment card|instant or sorcery card|card), (?:reveal it, )?put (?:it|that card) (?P<to>into your hand|onto the battlefield tapped|onto the battlefield), then shuffle")
def _tutor(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    to = {"into your hand": "hand", "onto the battlefield tapped": "battlefield_tapped", "onto the battlefield": "battlefield"}[m["to"]]
    return [{"do": "search", "who": "you", "filter": SEARCH_FILTERS[m["what"]], "to": to,
             "reveal": "reveal it" in m.group(0)}], None


@effect(r"you become the monarch")
def _monarch(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "monarch", "who": "you"}], None


@effect(r"draw {N} cards?, then discard {M} cards?")
def _loot(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "draw", "who": "you", "n": num(m["n"])}, {"do": "discard", "who": "you", "n": num(m["m"])}], None


class _NoMatch(Exception):
    """A template that matched the shape but not the details (e.g. an unknown keyword)."""


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s[:1].isupper() and not s.startswith("~") else s


def parse_effects(body: str) -> tuple[list[dict[str, Any]], str | None, bool] | None:
    """One sentence (or two joined by ". ") of effects → (effects, target selector, optional)."""
    body = body.strip()
    if not body.endswith("."):
        return None
    optional = False
    effects: list[dict[str, Any]] = []
    target: str | None = None
    for sentence in [s for s in re.split(r"(?<=\.)\s+", body) if s]:
        text = _lower_first(sentence.rstrip(".").strip())
        if text.startswith("you may "):
            if effects:
                return None  # "…. You may …" mid-ability: not a simple optional trigger
            optional, text = True, text[len("you may "):]
        for pattern, build in EFFECTS:
            m = pattern.match(text)
            if m:
                try:
                    found, sel = build(m)
                except _NoMatch:
                    return None
                if sel and target and sel != target:
                    return None  # two different targets: not supported yet
                target = sel or target
                effects += found
                break
        else:
            return None
    return effects, target, optional


def define(ability: AbilityText, ch: Characteristics) -> Definition | None:
    """The engine definition of one ability, or None (manual)."""
    text = self_text(ability.text, ch.name)
    if ability.kind == "static" and text == "~ enters tapped.":
        return {"kind": "replacement", "replacement": "enters_tapped", "effects": []}
    if ability.kind == "static" and text in COMBAT_STATICS:
        return {"kind": "static", "static": COMBAT_STATICS[text], "effects": []}
    if ability.kind == "triggered":
        for pattern, trigger in TRIGGERS:
            m = pattern.match(text)
            if m:
                parsed = parse_effects(m["body"])
                if parsed is None:
                    return None
                effects, target, optional = parsed
                out = {"kind": "triggered", "trigger": trigger, "effects": effects, "optional": optional,
                       "target": {"what": target} if target else None}
                if "filter" in pattern.groupindex:
                    out["filter"] = m["filter"]
                return out
        return None
    if ability.kind == "spell":
        parsed = parse_effects(text)
        if parsed is None or parsed[2]:
            return None
        effects, target, _ = parsed
        return {"kind": "spell", "effects": effects, "target": {"what": target} if target else None}
    if ability.kind == "activated" and ability.cost:
        cost = parse_ability_cost(ability.cost, card_name=ch.name)
        if cost.unsupported:
            return None
        parsed = parse_effects(text.split(":", 1)[1])
        if parsed is None or parsed[2]:
            return None
        effects, target, _ = parsed
        return {"kind": "activated", "cost": ability.cost, "effects": effects, "target": {"what": target} if target else None}
    return None


@lru_cache(maxsize=20000)
def _cached(ch: Characteristics) -> dict[int, Definition]:
    out = {}
    for ab in ch.abilities:
        d = define(ab, ch)
        if d is not None:
            out[ab.index] = d
    return out


def definitions(ch: Characteristics) -> dict[int, Definition]:
    """Engine definitions for a card's abilities, by ability index (see ``app.rules.oracle``).
    Hand-written scripts (``app.rules.cards``) are consulted by the caller first."""
    if ch.is_ability or ch.face_down:
        return {}
    from app.rules import cards  # hand-written scripts (a leaf package)

    if cards.get(ch.oracle_id) is not None and cards.trusted(ch.oracle_id, ch.oracle_text) is None:
        return {}  # REVIEW: a reviewed script exists for other Oracle text; nothing is automated until re-checked
    return _cached(replace(ch, pt=None, granted=frozenset(), lost=frozenset()))


# Combat restrictions and requirements printed on a permanent (CR 508.1c-d, 509.1b-c).
COMBAT_STATICS = {
    "~ can't block.": "cant_block",
    "~ can't attack.": "cant_attack",
    "~ can't attack or block.": "cant_attack_or_block",
    "~ can't be blocked.": "cant_be_blocked",
    "~ attacks each combat if able.": "must_attack",
    "~ can block only creatures with flying.": "block_only_flying",
    "~ can't be blocked by more than one creature.": "max_one_blocker",
}


def statics(ch: Characteristics) -> set[str]:
    """The combat statics a card has (from its definitions)."""
    return {d["static"] for d in definitions(ch).values() if d["kind"] == "static"}


# Keyword abilities that are triggered abilities (CR 702), as template definitions.
KEYWORD_TRIGGERS: dict[str, Definition] = {
    # 702.108 prowess: "Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn."
    "prowess": {"kind": "triggered", "trigger": "cast_you", "filter": "a noncreature spell",
                "effects": [{"do": "pump", "who": "self", "p": 1, "t": 1}], "optional": False, "target": None},
}


def keyword_triggers(ch: Characteristics) -> list[tuple[int, Definition]]:
    """Triggered keyword abilities of a card, with keys that can't clash with ability indexes."""
    if ch.is_ability or ch.face_down:
        return []
    out = []
    for ab in ch.abilities:
        if ab.kind != "keywords":
            continue
        for k, kw in enumerate(ab.keywords):
            if kw in KEYWORD_TRIGGERS:
                out.append((1000 + ab.index * 10 + k, KEYWORD_TRIGGERS[kw]))
    return out


def spell_definition(ch: Characteristics) -> Definition | None:
    """A whole instant/sorcery as one definition, if every line is automated (else None)."""
    if not ch.is_instant_or_sorcery:
        return None
    defs = definitions(ch)
    lines = [ab for ab in ch.abilities if ab.kind != "keywords"]
    if not lines or any(ab.index not in defs or defs[ab.index]["kind"] != "spell" for ab in lines):
        return None
    targets = [defs[ab.index]["target"] for ab in lines if defs[ab.index].get("target")]
    if len({t["what"] for t in targets}) > 1:
        return None
    return {"kind": "spell", "effects": [e for ab in lines for e in defs[ab.index]["effects"]],
            "target": targets[0] if targets else None}
