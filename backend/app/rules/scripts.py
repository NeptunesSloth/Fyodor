"""Declarative ability definitions from Oracle text: the template library.

A card ability the engine automates is described as **data**: a trigger (or spell / activated /
replacement), an optional target, and a list of effects built from the primitives in
``app.rules.effects``. Common Oracle wordings map onto templates here, so one tested mechanic
unlocks every card that uses it. Nothing is ever evaluated or executed from card text; a line
either matches a known template completely or it stays manual.

Definition shape (JSON-able)::

    {"kind": "triggered" | "spell" | "activated" | "replacement" | "static",  # (static: app/rules/statics.py)
     "trigger": "enters_self" | "dies_self" | "ltb_self" | "upkeep_you" | "end_step_you" | "attacks_self",
     "optional": bool,                       # "you may …": asked on resolution (603.5)
     "target": {"what": "creature" | "any" | …} or None,   # one "target [something]", one target
     # or target groups (115.1, 601.2c-d), one per word "target" in printed order; effects name
     # them "target:<g>" and a divided amount {"divided": g}:
     "targets": [{"what": sel, "min": 0, "max": 2, "distinct_from": [0], "divide": {"what": "damage", "total": 3}}],
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
from app.rules.oracle import AbilityText, parse_abilities
from app.rules.values import UNMODELED_COUNTERS

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
    "target attacking or blocking creature": "attacking_or_blocking_creature",
    "target nonland permanent an opponent controls": "nonland_permanent_opp",
    "target artifact or enchantment an opponent controls": "artifact_or_enchantment_opp",
    "target creature or planeswalker an opponent controls": "creature_or_planeswalker_opp",
    "target spell": "spell",
    "target creature spell": "creature_spell",
    "target noncreature spell": "noncreature_spell",
    "target instant or sorcery spell": "instant_or_sorcery_spell",
    "target attacking creature": "attacking_creature",
    "target blocking creature": "blocking_creature",
}
_SEL = "|".join(sorted((re.escape(k) for k in SELECTORS), key=len, reverse=True))

TRIGGERS = [
    (re.compile(r"^When ~ enters, (?P<body>.+)$"), "enters_self"),
    (re.compile(r"^When ~ dies, (?P<body>.+)$"), "dies_self"),
    (re.compile(r"^When ~ leaves the battlefield, (?P<body>.+)$"), "ltb_self"),
    (re.compile(r"^At the beginning of your upkeep, (?P<body>.+)$"), "upkeep_you"),
    (re.compile(r"^At the beginning of your end step, (?P<body>.+)$"), "end_step_you"),
    (re.compile(r"^Whenever ~ attacks, (?P<body>.+)$"), "attacks_self"),
    (re.compile(r"^Whenever ~ enters or attacks, (?P<body>.+)$"), "enters_or_attacks_self"),
    (re.compile(r"^(?:Landfall — )?Whenever a land you control enters, (?P<body>.+)$"), "landfall"),
    (re.compile(r"^When ~ becomes the target of a spell or ability, (?P<body>.+)$"), "targeted_self"),
    (re.compile(r"^Whenever ~ deals combat damage to a player, (?P<body>.+)$"), "combat_damage_player_self"),
    (re.compile(r"^Whenever (?P<filter>another creature you control|a creature you control|another nontoken creature you control|"
                r"a nontoken creature you control|another creature|a creature) enters, (?P<body>.+)$"), "enters_other"),
    # 503.1a / 504 / 505 / 507 / 513: "At the beginning of [whose] [step]" (generic: see step_trigger)
    (re.compile(r"^At the beginning of (?:(?P<whose>your|each|each player's|each opponent's|the|enchanted player's) "
                r"(?P<step>upkeep|draw step|end step|first main phase|precombat main phase|second main phase|"
                r"postcombat main phase)|the (?P<hstep>upkeep|end step) of enchanted (?:creature|permanent|land|artifact|"
                r"enchantment)'s controller|combat on (?P<cwhose>your|each opponent's) turn|(?P<each_combat>each combat)), "
                r"(?P<body>.+)$"), "step"),
    (re.compile(r"^Whenever you cast (?P<filter>a spell|a creature spell|a noncreature spell|an instant or sorcery spell|"
                r"an artifact spell|an enchantment spell), (?P<body>.+)$"), "cast_you"),
    # Anything else "When/Whenever [subject] [event], …": the generic condition grammar (app/rules/events.py)
    (re.compile(r"^(?:When|Whenever) (?P<cond>[^,]+), (?P<body>.+)$"), "event"),
]


STEPS = {"upkeep": "upkeep", "draw step": "draw", "end step": "end", "first main phase": "main1",
         "precombat main phase": "main1", "second main phase": "main2", "postcombat main phase": "main2"}
WHOSE = {"your": "you", "each": "each", "each player's": "each", "the": "each", "each opponent's": "opponent",
         "enchanted player's": "enchanted_player"}


def step_trigger(m: re.Match[str]) -> str:
    """"step:<phase>:<whose>": whose step it is decides whether it triggers (at_step)."""
    if m["each_combat"]:
        return "step:begin_combat:each"
    if m["cwhose"]:
        return f"step:begin_combat:{WHOSE[m['cwhose']]}"
    if m["hstep"]:
        return f"step:{STEPS[m['hstep']]}:host_controller"
    return f"step:{STEPS[m['step']]}:{WHOSE[m['whose']]}"


_LEGACY_SELF = {"enter": "enters_self", "die": "dies_self", "leave": "ltb_self", "attack": "attacks_self",
                "deal_combat_damage_player": "combat_damage_player_self"}


def _legacy_trigger(cond: dict[str, Any]) -> str | None:
    """Self conditions the engine already fires by name ("When ~ dies" → dies_self)."""
    if cond.get("subject") == "self" and cond["event"] in _LEGACY_SELF:
        return _LEGACY_SELF[cond["event"]]
    if cond.get("event") == "multi":
        return "multi:" + "+".join(_LEGACY_SELF[e] for e in cond["events"])
    return None


def num(word: str) -> int:
    return int(word) if word.isdigit() else NUMBERS[word.lower()]


def _signed(p: str) -> int:
    return -int(p[1:]) if p[0] in "-−" else int(p.lstrip("+"))


# 207.2c: ability words tie abilities together but have no rules meaning
ABILITY_WORDS = (
    "adamant", "addendum", "alliance", "battalion", "bloodrush", "celebration", "channel", "chroma", "cohort",
    "constellation", "converge", "council's dilemma", "coven", "delirium", "descend 4", "descend 8", "disappear",
    "domain", "eerie", "eminence", "enrage", "fateful hour", "fathomless descent", "ferocious", "flurry", "formidable",
    "grandeur", "hellbent", "heroic", "imprint", "infusion", "inspired", "join forces", "kinship", "landfall",
    "lieutenant", "magecraft", "metalcraft", "morbid", "opus", "pack tactics", "paradox", "parley", "radiance", "raid",
    "rally", "renew", "repartee", "revolt", "secret council", "spell mastery", "strive", "survival", "sweep",
    "tempting offer", "threshold", "undergrowth", "valiant", "vivid", "void", "will of the council")
_ABILITY_WORD = re.compile(r"^(?:" + "|".join(re.escape(w).replace("'", "['’]") for w in ABILITY_WORDS) + r") — ",
                           re.IGNORECASE)


def _short_name(name: str) -> str | None:
    """How Oracle text shortens a name like "Sharuum the Hegemon" or "Zur the Enchanter" (the
    first word), unless that word is also a creature type ("Soldier of the Pantheon")."""
    from app.rules.creature_types import CREATURE_TYPES

    m = re.match(r"^([A-Z][\w'-]{2,}) (?:the|of) ", name)
    if m is None or m[1] in CREATURE_TYPES or m[1].rstrip("s") in CREATURE_TYPES:
        return None
    return m[1]


def self_text(text: str, name: str) -> str:
    """The ability with the card's own name (and "this creature" etc.) written as ~, without an
    ability word (207.2c)."""
    out = _ABILITY_WORD.sub("", text, count=1)
    short = _short_name(name)
    for n in sorted({name, name.split(",")[0].strip(), *([short] if short else [])}, key=len, reverse=True):
        if len(n) >= 3:
            out = re.sub(rf"\b{re.escape(n)}\b", "~", out)
    return re.sub(r"\b[Tt]his (creature|artifact|enchantment|land|permanent|planeswalker|battle|Equipment|Vehicle|Aura)\b", "~", out)


EFFECTS: list[tuple[re.Pattern[str], Any]] = []


def _self_or_it(word: str) -> str:
    """"~" is the source; "it" is a pronoun resolved later against its antecedent (resolve_it)."""
    return "it" if word == "it" else "self"


def _it_source(word: str) -> dict[str, str]:
    """"It deals …" / "It explores": the pronoun names the object doing it (resolve_it)."""
    return {"src": "it"} if word == "it" else {}


# Events after which the object is still where it was, so "it" can name it (not dies / leaves:
# that's a new object in another zone, 400.7)
_STAYING = {"enter", "attack", "block", "blocked", "tapped", "untapped", "dealt_damage", "deal_damage_opponent",
            "deal_combat_damage_player"}


def _condition_says_other(cond: dict[str, Any]) -> bool:
    from app.rules import selectors  # (a leaf module)

    key = (cond.get("value") or {}).get("count")
    return isinstance(key, str) and selectors.from_key(key).other


def _trigger_antecedent(name: str, cond: dict[str, Any] | None) -> str | None:
    """What "it" / "that creature" means in a triggered ability's effect: this object when the
    trigger is about it; the object the event happened to ("Whenever another creature you control
    enters, put a +1/+1 counter on it"), bound when it triggers; else nothing (manual)."""
    if name in ("dies_self", "ltb_self") or name.startswith("multi:"):
        # it left the battlefield: "it" is a new object elsewhere (400.7), which the engine
        # doesn't follow yet; it may still be the source of damage (last known information)
        return "self_gone"
    if name.endswith("_self") or (cond or {}).get("subject") == "self":
        return "self"
    if name in ("enters_other", "landfall"):
        return "event"
    if cond and cond.get("subject") in ("sel", "self_or") and not cond.get("aggregate") and cond["event"] in _STAYING:
        return "event"
    return None


def _group_of(e: dict[str, Any]) -> int | None:
    """The target group an effect acts on ("target:<g>"; plain "target" is group 0)."""
    who = e.get("who")
    if who == "target":
        return 0
    if isinstance(who, str) and who.startswith("target:"):
        return int(who[7:])
    return None


def resolve_it(effects: list[dict[str, Any]], antecedent: str | None,
               groups: list[dict[str, Any]] | None = None) -> list[dict[str, Any]] | None:
    """Resolve the pronouns in parsed effects (placeholders "who": "it" / "them", "src": "it"):
    after a target in the same ability, "it" is that target ("Untap target creature. It gets
    +1/+4") — if that "target" allows one target; after "up to two target creatures" "it" is
    ambiguous (None) — and "them" / "each of them" are the targets of the last group; otherwise
    "it" is ``antecedent`` ("self" for "When ~ dies, return it …"). None when a pronoun names
    something the engine doesn't track (the triggering object of "Whenever another creature
    enters, put a counter on it", a spell just cast, …): the ability stays manual."""
    out: list[dict[str, Any]] = []
    last: int | None = None
    previous: int | None = None  # the group the previous instruction acted on
    for e in effects:
        e = dict(e)
        if e.get("who") == "them":
            if previous is None:
                return None  # ("them" after something that wasn't those targets: not followed)
            e["who"] = "target" if groups is None else f"target:{previous}"
        if e.get("who") == "it":
            if last is not None:
                if groups is not None and groups[last]["max"] != 1:
                    return None  # "it" after several targets: which one? (manual)
                e["who"] = "target" if groups is None else f"target:{last}"
            elif antecedent in ("self", "event"):
                e["who"] = antecedent
            else:
                return None
        if e.get("src") == "it":
            if last is not None or antecedent not in ("self", "self_gone"):
                return None  # (the target, not the source, deals the damage / explores)
            del e["src"]
        g = _group_of(e)
        last = g if g is not None else last
        previous = g
        out.append(e)
    return out


_TARGET_REFS = ("who", "power", "toughness", "mana_value", "on")


def _renumber(value: Any, index: list[int] | None) -> Any:
    """Rewrite a clause's own target references ("target" = its first group, "target:<k>", n
    {"divided": k}) to the ability's group numbers (``index[k]``); ``index`` None: back to the
    plain "target" of an ability with one simple target."""
    if isinstance(value, list):
        return [_renumber(v, index) for v in value]
    if not isinstance(value, dict):
        return value
    out = {}
    for k, v in value.items():
        if k in _TARGET_REFS and isinstance(v, str) and (v == "target" or v.startswith("target:")):
            local = 0 if v == "target" else int(v[7:])
            v = "target" if index is None else f"target:{index[local]}"
        elif k == "divided" and isinstance(v, int):
            if index is None:
                raise _NoMatch
            v = index[v]
        else:
            v = _renumber(v, index)
        out[k] = v
    return out


def _as_groups(sel: Any) -> list[dict[str, Any]]:
    """A clause's targets (None, a selector key, one group, several) as target groups."""
    if sel is None:
        return []
    if isinstance(sel, str):
        return [{"what": sel, "min": 1, "max": 1}]
    return [dict(g) for g in ([sel] if isinstance(sel, dict) else sel)]


def _add_groups(groups: list[dict[str, Any]], found: list[dict[str, Any]], sel: Any) -> list[dict[str, Any]]:
    """Append a clause's target groups to the ability's: every word "target" is its own group
    (115.3, 601.2c). "another target …" after an earlier target of the ability can't be the same
    object as those; with no earlier target it means other than the source (as before)."""
    index = []
    for g in _as_groups(sel):
        if "another" in g:
            plain = g.pop("another")
            if groups:
                g = {**g, "what": plain, "distinct_from": list(range(len(groups)))}
            elif not g["what"]:
                raise _NoMatch  # "another target" with nothing before it
        index.append(len(groups))
        groups.append(g)
    return _renumber(found, index)


def _finish_targets(effects: list[dict[str, Any]], groups: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Any]:
    """(effects, the definition's targets): one simple target keeps the plain "target" shape
    (``"target": {"what": key}``); anything else is a list of groups (``"targets"``)."""
    from app.rules.language import simple

    if not groups:
        return effects, None
    if len(groups) == 1 and simple(groups[0]):
        return _renumber(effects, None), groups[0]["what"]
    return effects, groups


def target_fields(target: Any) -> dict[str, Any]:
    """The definition keys for parsed targets: "target" (one simple target, or None) and, for
    target groups, "targets": [{"what", "min", "max", "distinct_from"?, "divide"?}, …]."""
    if target is None or isinstance(target, str):
        return {"target": {"what": target} if target else None}
    return {"target": None, "targets": target}


def target_groups(definition: dict[str, Any] | None) -> list[dict[str, Any]]:
    """A definition's target groups in printed order (601.2c); the old single "target" is one
    group of exactly one target."""
    if not definition:
        return []
    if definition.get("targets"):
        return [{"min": 1, "max": 1, **g} for g in definition["targets"]]
    spec = definition.get("target")
    return [{**spec, "min": 1, "max": 1}] if spec else []


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


@effect(r"(?P<src>~|it) deals {N} damage to (?P<sel>{SEL})")
def _damage(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "damage", "who": "target", "n": num(m["n"]), **_it_source(m["src"])}], SELECTORS[m["sel"]]


@effect(r"~ deals {N} damage to each opponent")
def _damage_opponents(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "damage", "who": "each_opponent", "n": num(m["n"])}], None


@effect(r"~ deals {N} damage to each creature")
def _damage_creatures(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "damage", "who": "each_creature", "n": num(m["n"])}], None


@effect(r"(?P<sel>target creature|target creature you control) gets (?P<p>[+−-]\d+)/(?P<t>[+−-]\d+) until end of turn")
def _pump_target(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "pump", "who": "target", "p": _signed(m["p"]), "t": _signed(m["t"])}], SELECTORS[m["sel"]]


@effect(r"(?P<who>~|it) gets (?P<p>[+−-]\d+)/(?P<t>[+−-]\d+) until end of turn")
def _pump_self(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "pump", "who": _self_or_it(m["who"]), "p": _signed(m["p"]), "t": _signed(m["t"])}], None


@effect(r"creatures you control get (?P<p>[+−-]\d+)/(?P<t>[+−-]\d+) until end of turn")
def _pump_team(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "pump", "who": "creatures_you_control", "p": _signed(m["p"]), "t": _signed(m["t"])}], None


_KW = "|".join(GRANTABLE)


@effect(rf"(?P<who>target creature|~|it) gains (?P<kw>{_KW}) until end of turn")
def _grant(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    who = "target" if m["who"].startswith("target") else _self_or_it(m["who"])
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


@effect(r"create {N} (?P<pt>\d+/\d+) " + _COLORS_RE + r" (?P<sub>[A-Z][A-Za-z'\-]*(?: [A-Z][A-Za-z'\-]*)*) (?P<ench>enchantment )?(?P<art>artifact )?creature tokens?"
        r"(?: with (?P<kws>[a-z ,]+?)| with \"(?P<quoted>[^\"]+)\")?")
def _create_creature(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    p, t = m["pt"].split("/")
    colors = [] if m["colors"] == "colorless" else [COLOR_WORDS[w] for w in re.findall(r"white|blue|black|red|green", m["colors"])]
    kws = [k.strip() for k in re.split(r", and |, | and ", m["kws"] or "") if k.strip()]
    if any(k not in GRANTABLE and k not in ("defender",) for k in kws):
        raise _NoMatch
    type_line = f"Token {'Enchantment ' if m['ench'] else ''}{'Artifact ' if m['art'] else ''}Creature — {m['sub']}"
    text = "\n".join(k.capitalize() for k in kws)
    if m["quoted"]:
        text = _granted_token_text(m["quoted"])
    return [{"do": "create_token", "who": "you", "n": num(m["n"]),
             "token": {"name": m["sub"], "power": p, "toughness": t, "colors": colors, "type_line": type_line, "text": text}}], None


def _granted_token_text(quoted: str) -> str:
    """The quoted ability a token is created with; only ones the engine carries out (a mana
    ability such as an Eldrazi Spawn's "Sacrifice this token: Add {C}.")."""
    from app.rules.mana import parse_mana_ability

    if parse_mana_ability(quoted) is None:
        raise _NoMatch
    return quoted


@effect(r"(?:it has|they have) \"(?P<quoted>[^\"]+)\"")
def _token_has(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "token_text", "text": _granted_token_text(m["quoted"])}], None


@effect(r"create {N} (?P<kind>Treasure|Food|Gold|Clue|Blood|Shard|Powerstone|Heartwood) tokens?")
def _create_predefined(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    type_line, text = PREDEFINED_TOKENS[m["kind"]]
    return [{"do": "create_token", "who": "you", "n": num(m["n"]),
             "token": {"name": m["kind"], "power": None, "toughness": None, "colors": [], "type_line": type_line, "text": text}}], None


@effect(r"put {N} (?P<kind>\+1/\+1|-1/-1) counters? on (?P<who>target creature you control|target creature|~|it|each creature you control)")
def _counters(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    who = {"~": "self", "it": "it", "each creature you control": "creatures_you_control"}.get(m["who"], "target")
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


@effect(r"return {N} (?P<what>lands?|creatures?) you control to (?:its|their) owner's hands?")
def _return_yours(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "return_yours", "n": num(m["n"]), "what": "land" if m["what"].startswith("land") else "creature"}], None


@effect(r"counter (?P<sel>target spell|target creature spell|target noncreature spell|target instant or sorcery spell)")
def _counter(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "counter", "who": "target"}], SELECTORS[m["sel"]]


@effect(r"counter (?P<sel>target spell|target creature spell|target noncreature spell|target instant or sorcery spell)"
        r" unless its controller pays (?P<cost>(?:\{{[^}}]+\}})+)")
def _counter_unless(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "counter_unless", "who": "target", "cost": m["cost"]}], SELECTORS[m["sel"]]


@effect(r"prevent the next {N} damage that would be dealt to (?P<sel>any target|target creature|target player|~) this turn")
def _prevent(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    if m["sel"] == "~":
        return [{"do": "prevent", "who": "self", "n": num(m["n"])}], None
    return [{"do": "prevent", "who": "target", "n": num(m["n"])}], SELECTORS[m["sel"]]


@effect(r"(?:this spell|~) can't be countered")
def _uncounterable(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [], None  # a property of the spell (see uncounterable), not an effect


def uncounterable(ch: Characteristics) -> bool:
    """"This spell can't be countered." / "~ can't be countered." on the card."""
    return any(self_text(ab.text, ch.name).rstrip(".") in ("This spell can't be countered", "~ can't be countered")
               for ab in ch.abilities)


@effect(r"mill {N} cards?")
def _mill(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "mill", "who": "you", "n": num(m["n"])}], None


@effect(r"exile (?P<sel>{SEL}) until ~ leaves the battlefield")
def _exile_until(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "exile_until", "who": "target"}], SELECTORS[m["sel"]]


@effect(r"investigate")
def _investigate(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    type_line, text = PREDEFINED_TOKENS["Clue"]
    return [{"do": "create_token", "who": "you", "n": 1,
             "token": {"name": "Clue", "power": None, "toughness": None, "colors": [], "type_line": type_line, "text": text}}], None


@effect(r"(?P<src>~|it) explores")
def _explore(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "explore", **_it_source(m["src"])}], None


@effect(r"sacrifice (?P<who>~|it)")
def _sacrifice_self(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "sacrifice", "who": _self_or_it(m["who"])}], None


@effect(r"activate only once each turn")
def _once_each_turn(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [], None  # an activation restriction (enforced by casting.ability_problem), not an effect


@effect(r"sacrifice ~ unless you pay (?P<cost>(?:\{{[^}}]+\}})+)")
def _pay_or_sacrifice(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "pay_or_sacrifice", "cost": m["cost"]}], None


@effect(r"(?:it|they) can't be regenerated")
def _no_regeneration(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "no_regen"}], None  # the destruction of this spell/ability ignores regeneration shields


@effect(r"regenerate (?P<who>~|it|target creature|target creature you control)")
def _regenerate(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    if m["who"] in ("~", "it"):
        return [{"do": "regenerate", "who": _self_or_it(m["who"])}], None
    return [{"do": "regenerate", "who": "target"}], SELECTORS[m["who"]]


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


def _one_clause(text: str) -> tuple[list[dict[str, Any]], Any] | None:
    """One instruction: a literal template, else the generic grammar (app/rules/language.py)."""
    from app.rules import language  # the generic grammar (a leaf module)

    for pattern, build in EFFECTS:
        m = pattern.match(text)
        if m:
            try:
                found, sel = build(m)
            except _NoMatch:
                return None
            if found and found[0]["do"] == "token_text":
                return None
            return found, sel
    return language.parse_sentence(text)


def _clause(text: str) -> tuple[list[dict[str, Any]], Any] | None:
    """An instruction, or two joined by ", then" / "and" ("Scry 1, then draw a card.", "You draw
    two cards and you lose 2 life."): each half must be understood. Each "target" word is its
    own target group (115.3); the halves' groups are numbered in order."""
    found = _one_clause(text)
    if found is not None:
        return found
    for joiner in (r", then ", r" and (?=(?:you|target|each|~|it|that player|draw|lose|gain|put|return|exile|"
                                 r"destroy|tap|untap|create|sacrifice|discard|mill|scry|surveil)\b)"):
        parts = re.split(joiner, text, maxsplit=1)
        if len(parts) != 2:
            continue
        # "Target player draws a card, then discards a card": the right half's subject is the
        # left's (608.2c reads the whole text), not "you"
        subj = re.match(r"^(target player|target opponent|each player|each opponent|each of your opponents|"
                        r"that player) ", parts[0])
        same_target = False
        if subj and re.match(r"^(?:draws|discards|mills|loses|gains|sacrifices|shuffles|puts|reveals|exiles|"
                             r"returns|creates|searches|scry|surveil)\b", parts[1]):
            parts[1] = f"{subj[1]} {parts[1]}"
            same_target = subj[1].startswith("target")  # (one word "target": the same target)
        left, right = _clause(parts[0]), _clause(parts[1])
        if left is None or right is None:
            continue
        lgroups, rgroups = _as_groups(left[1]), _as_groups(right[1])
        if same_target:
            if not lgroups or len(rgroups) != 1:
                continue
            return left[0] + _renumber(right[0], [0]), left[1]
        groups = lgroups + rgroups
        index = list(range(len(lgroups), len(groups)))
        return _renumber(left[0], list(range(len(lgroups)))) + _renumber(right[0], index), groups or None
    return None


def parse_effects(body: str, it: str | None = None) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """One sentence (or two joined by ". ") of effects → (effects, targets, optional). Targets:
    None, a selector key (one "target [something]"), or a list of target groups (see
    target_fields). ``it``: what the pronoun "it" means when no target precedes it (resolve_it)."""
    try:
        return _parse_effects(body, it)
    except _NoMatch:
        return None


def _parse_effects(body: str, it: str | None) -> tuple[list[dict[str, Any]], Any, bool] | None:
    body = body.strip()
    if not body.endswith(".") and not body.endswith('."'):
        return None
    optional = False
    effects: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    start = 0
    sentences = [s for s in re.split(r"(?<=\.)\s+", body) if s]
    for i, sentence in enumerate(sentences):
        text = _lower_first(sentence.rstrip(".").strip())
        prev_start, start = start, len(effects)
        if (kicked := _KICKED.match(text)) is not None:
            with_kicker = _kicked_sentence(kicked, effects, prev_start)
            if with_kicker is None:
                return None
            effects = with_kicker
            continue
        # "You may pay {2}. If you do, …" (118.12): the cost is an effect that records whether it
        # was paid; "If you do" / "If you don't" then gates the sentence on that payment
        if (paid := _may_pay_sentence(text, sentences[i + 1:i + 2], it, effects)) is not None:
            effects.append(paid)
            continue
        if (if_do := _IF_YOU_DO.match(text)) is not None:
            bind = _last_payment(effects)
            inner = _clause(if_do["rest"]) if bind is not None and not if_do["rest"].startswith("you may ") else None
            if inner is None:
                return None
            added = _add_groups(groups, *inner)
            gate: dict[str, Any] = {"succeeded": bind, **({"negate": True} if if_do["neg"] else {})}
            effects += [{"do": "only_if", "cond": gate, "skip": len(added)}, *added]
            continue
        cond_m = re.match(r"^if (?P<c>[^,]+), (?P<rest>.+)$", text)
        if cond_m:  # "If you control a Forest, draw a card." (608.2c): a condition on this sentence
            from app.rules import conditions

            cond = conditions.parse(cond_m["c"])
            inner = _clause(cond_m["rest"]) if cond is not None and not cond_m["rest"].startswith("you may ") else None
            if inner is None:
                return None
            added = _add_groups(groups, *inner)  # (its target, if any: its own group, 115.3)
            effects += [{"do": "only_if", "cond": cond, "skip": len(added)}, *added]
            continue
        if text.startswith("you may "):
            if effects:
                # "…. You may reveal … from among them …": a clause that models its own choice
                own = _clause(text)
                if own is None or not any(x.get("optional") for x in own[0]):
                    return None  # "…. You may …" mid-ability: not a simple optional trigger
                effects += _add_groups(groups, own[0], own[1])
                continue
            optional, text = True, text[len("you may "):]
        for pattern, build in EFFECTS:
            m = pattern.match(text)
            if m:
                found, sel = build(m)
                if found and found[0]["do"] == "token_text":  # "It has "…"": the token just created
                    if not effects or effects[-1]["do"] != "create_token":
                        return None
                    effects[-1] = {**effects[-1], "token": {**effects[-1]["token"], "text": found[0]["text"]}}
                    break
                effects += _add_groups(groups, found, sel)  # each word "target": its own group (115.3)
                break
        else:
            parsed_clause = _unless_sentence(text, effects) or _clause(text)
            if parsed_clause is None:
                return None
            found, sel = parsed_clause
            effects += _add_groups(groups, found, sel)
    resolved = resolve_it(effects, it, groups)
    if resolved is None:
        return None
    resolved, target = _finish_targets(resolved, groups)
    looked = False
    for e in resolved:  # "… from among them" needs the cards a look put aside (not milled ones)
        looked = looked or e["do"] == "look_top"
        if e["do"] in ("pick_looked", "rest_looked") and not looked:
            return None
    return resolved, target, optional


_KICKED = re.compile(r"^if (?:this spell|it|~) was kicked, (?P<instead1>instead )?(?P<rest>.+?)(?P<instead2> instead)?$")


# -- optional payments (118.12 / 118.12a): app/rules/optional_payment.py ------------------------------
_IF_YOU_DO = re.compile(r"^if you (?:(?P<neg>don't)|do), (?P<rest>.+)$")
_UNLESS = re.compile(r"^(?P<lead>.+?) unless (?P<who>you|that player|they|its controller|that creature's controller) "
                     r"pays? (?P<cost>.+)$")


def _last_payment(effects: list[dict[str, Any]]) -> str | None:
    """The binding of the most recent optional payment ("If you do" refers to it)."""
    return next((e["bind"] for e in reversed(effects) if e["do"] == "optional_payment"), None)


def _may_pay_sentence(text: str, following: list[str], it: str | None,
                      effects: list[dict[str, Any]]) -> dict[str, Any] | None:
    """"You may [cost]." when the next sentence is "If you do, …" / "If you don't, …": the cost as
    an optional_payment effect, bound as pay<k>. A cost about "it" is only read when "it" is this
    object (the trigger's own source); "When you do" (a reflexive trigger, 603.12) isn't read."""
    from app.rules import optional_payment

    if not text.startswith("you may ") or not following or not re.match(r"^If you (?:do|don't), ", following[0]):
        return None
    phrase = text[len("you may "):]
    if re.search(r"\bit\b", phrase) and it != "self":
        return None
    cost = optional_payment.cost_text(phrase)
    if cost is None:
        return None
    bind = f"pay{sum(1 for e in effects if e['do'] == 'optional_payment')}"
    return {"do": "optional_payment", "who": "you", "cost": cost, "bind": bind}


def _unless_sentence(text: str, effects: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Any] | None:
    """"[Effect] unless [you / that player / they / its controller] pay(s) [cost]." (118.12a): the
    payer may pay; if they don't, the effect happens. "That player" / "they" is the effect's
    target player or the trigger event's player; "its controller" the controller of the effect's
    target object. Several payers ("each opponent … unless they pay") aren't read."""
    from app.rules import optional_payment

    m = _UNLESS.match(text)
    if m is None or re.search(r"\bit\b", m["cost"]):
        return None
    cost = optional_payment.cost_text(m["cost"])
    lead = _clause(m["lead"])
    if cost is None or lead is None or not lead[0]:
        return None
    found, sel = lead
    groups = _as_groups(sel)
    who = m["who"]
    whos = {e.get("who") for e in found}
    group_player = bool(groups) and _player_target(groups[0]["what"])
    if who == "you":
        payer = "you"
    elif who in ("its controller", "that creature's controller"):
        if "target" not in whos or not groups or group_player is not False:
            return None
        payer = "target"
    elif "target" in whos and groups and group_player:
        payer = "target"
    elif whos == {"event_player"}:
        payer = "event_player"
    else:
        return None
    bind = f"pay{sum(1 for e in effects if e['do'] == 'optional_payment')}"
    return [{"do": "optional_payment", "who": payer, "cost": cost, "bind": bind},
            {"do": "only_if", "cond": {"succeeded": bind, "negate": True}, "skip": len(found)}, *found], sel


def _player_target(what: str) -> bool | None:
    """Is a target group's selector a player (True), an object (False), or either ("any target": None)?"""
    from app.rules import selectors

    if what in ("player", "opponent"):
        return True
    if what == "any" or not what:
        return None
    return selectors.from_key(what).player is not None if what.startswith(selectors.PREFIX) else False


def _kicked_sentence(m: re.Match[str], effects: list[dict[str, Any]], prev_start: int) -> list[dict[str, Any]] | None:
    """702.33e: "If this spell was kicked, [effect]." — the effect happens only if it was kicked;
    "… instead" replaces the sentence before it when it was kicked. Kicked-only text may not add
    a target (702.33g: those targets are chosen only if it's kicked — not modeled yet)."""
    rest = m["rest"]
    if rest.startswith("you may ") or rest.startswith("instead "):
        return None
    found = _clause(rest)
    if found is None or found[1] is not None or not found[0]:
        return None
    alt = found[0]
    if m["instead1"] or m["instead2"]:
        base = effects[prev_start:]
        if not base or any(e["do"] == "kicked_gate" for e in base):
            return None
        return [*effects[:prev_start], {"do": "kicked_gate", "kicked": False, "n": len(base)}, *base,
                {"do": "kicked_gate", "kicked": True, "n": len(alt)}, *alt]
    return [*effects, {"do": "kicked_gate", "kicked": True, "n": len(alt)}, *alt]


ATTACHED_SUBJECTS = ("Enchanted creature", "Equipped creature", "Enchanted land")


@lru_cache(maxsize=4096)
def granted_ability(text: str) -> AbilityText | None:
    """A quoted ability granted by a static ("All Slivers have "…"") if the engine carries it out."""
    from app.rules.mana import parse_mana_ability

    parsed = parse_abilities(text)
    if len(parsed) != 1:
        return None
    ab = parsed[0]
    if ab.kind == "mana":
        return ab if parse_mana_ability(ab.text) is not None else None
    if ab.kind == "keywords":
        from app.rules.coverage import SUPPORTED_KEYWORDS

        return ab if set(ab.keywords) <= SUPPORTED_KEYWORDS else None
    probe = Characteristics(name="\u0000", abilities=(ab,))
    return ab if define(ab, probe) is not None else None


def parse_anthem(text: str) -> Definition | None:
    """613 static P/T, keyword and ability grants ("Creatures you control get +1/+1.", "Other Elves
    you control get +1/+1 and have haste.", "All Slivers have "{T}: Add one mana of any color."",
    "~ gets +2/+2 as long as you control three or more artifacts."): app/rules/statics.py."""
    from app.rules import statics  # (statics imports granted_ability from here)

    return statics.parse(text)


SHOCK = re.compile(r"^As ~ enters, you may pay (?P<n>\d+) life\. If you don't, it enters tapped\.$")
ENTERS_WITH = re.compile(r"^(?:(?P<kicked>If ~ was kicked, it)|~) enters with "
                         r"(?P<n>X|\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten) "
                         r"(?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on it(?P<each> for each time it was kicked)?\.$")


def define(ability: AbilityText, ch: Characteristics) -> Definition | None:
    """The engine definition of one ability, or None (manual)."""
    text = self_text(ability.text, ch.name)
    if ability.kind == "static" and text == "~ enters tapped.":
        return {"kind": "replacement", "replacement": "enters_tapped", "effects": []}
    m = SHOCK.match(text) if ability.kind == "static" else None
    if m:  # shock lands: "As ~ enters, you may pay 2 life. If you don't, it enters tapped."
        return {"kind": "replacement", "replacement": "pay_life_or_tapped", "life": int(m["n"]), "effects": []}
    m = ENTERS_WITH.match(text) if ability.kind == "static" else None
    if m and m["kind"] not in UNMODELED_COUNTERS:  # 614.1c: "~ enters with N … counters on it"
        n: int | str = "X" if m["n"] == "X" else num(m["n"])
        out: Definition = {"kind": "replacement", "replacement": "enters_with_counters", "counter": m["kind"], "n": n,
                           "effects": []}
        if m["kicked"]:  # 702.33e: "If ~ was kicked, it enters with …"
            out["if_kicked"] = True
        if m["each"]:  # "… for each time it was kicked" (multikicker, 702.33c)
            out["per_kick"] = True
        return out
    if ability.kind == "static" and (anthem := parse_anthem(text)) is not None:
        return anthem
    if ability.kind == "static" and (rule := attached_rule(text)) is not None:
        return rule
    if ability.kind == "static" and text == "~ can be your commander.":
        return {"kind": "static", "static": "deckbuilding", "effects": []}  # 903.3a: deck construction only
    if ability.kind == "static" and text in COMBAT_STATICS:
        return {"kind": "static", "static": COMBAT_STATICS[text], "effects": []}
    if ability.kind == "triggered":
        for pattern, trigger in TRIGGERS:
            m = pattern.match(text)
            if m:
                name = step_trigger(m) if trigger == "step" else trigger
                body = m["body"]
                kicked = re.match(r"^if (?:it|~) was kicked, (?P<rest>.+)$", body) if name == "enters_self" else None
                if kicked is not None:  # 603.4 intervening "if": checked as it triggers (triggers._add)
                    body = kicked["rest"]
                cond = None
                if trigger == "event":
                    from app.rules import events as event_grammar  # (a leaf module)

                    cond = event_grammar.parse_condition(m["cond"])
                    if cond is None:
                        return None
                    name = _legacy_trigger(cond) or "event"
                parsed = parse_effects(body, it=_trigger_antecedent(name, cond))
                if parsed is None:
                    return None
                effects, target, optional = parsed
                # 603.4: "When/Whenever/At …, if [condition], …" — an intervening "if": checked as it
                # triggers (triggers._add) and again as it resolves (the only_if effect)
                intervening = None
                if body.lower().startswith("if "):
                    if not effects or effects[0]["do"] != "only_if":
                        return None
                    # the whole ability, however many sentences follow: if it doesn't hold, the
                    # ability doesn't trigger, or does nothing as it resolves
                    intervening = effects[0]["cond"]
                    effects = [{**effects[0], "skip": len(effects) - 1}, *effects[1:]]
                if _trigger_antecedent(name, cond) != "self" and any(
                        e["do"] == "only_if" and _condition_says_other(e["cond"]) for e in effects):
                    return None  # ("other" than the object the event happened to, not ~: not modeled)
                out = {"kind": "triggered", "trigger": name,
                       "effects": effects, "optional": optional, **target_fields(target)}
                if cond is not None and name == "event":
                    out["cond"] = cond
                if intervening is not None:
                    out["if"] = intervening
                if kicked is not None:
                    out["if_kicked"] = True
                if "filter" in pattern.groupindex:
                    out["filter"] = m["filter"]
                return out
        return None
    if ability.kind == "spell":
        parsed = parse_effects(text)
        if parsed is None or parsed[2]:
            return None
        effects, target, _ = parsed
        return {"kind": "spell", "effects": effects, **target_fields(target)}
    if ability.kind == "loyalty" and ability.cost:
        # 606: a loyalty ability is an activated ability; its cost (loyalty counters) is paid on
        # activation (casting.activate_to_stack), its effect uses the same grammar
        cost = parse_ability_cost(ability.cost, card_name=ch.name, loyalty=True)
        if cost.unsupported:
            return None
        parsed = parse_effects(text.split(":", 1)[1])
        if parsed is None or parsed[2]:
            return None
        effects, target, _ = parsed
        return {"kind": "activated", "loyalty": True, "cost": ability.cost, "effects": effects,
                **target_fields(target)}
    if ability.kind == "activated" and ability.cost:
        cost = parse_ability_cost(ability.cost, card_name=ch.name)
        if cost.unsupported:
            return None
        parsed = parse_effects(text.split(":", 1)[1])
        if parsed is None or parsed[2]:
            return None
        effects, target, _ = parsed
        return {"kind": "activated", "cost": ability.cost, "effects": effects, **target_fields(target)}
    return None


# Trigger events that come with an amount ("that much"): life gained / lost, damage dealt
_AMOUNT_EVENTS = {"gain_life", "lose_life", "dealt_damage", "deal_damage_opponent", "deal_combat_damage_player"}


_PLAYER_EVENTS = {"deal_combat_damage_player", "deal_damage_opponent"}  # events with a player dealt damage


def _event_refs_ok(d: Definition) -> bool:
    """"That player" / "that much" name what a trigger event was about (its TriggerEvent): only a
    generic trigger condition whose event has that player or amount can use them. A "one or more"
    trigger has one event per batch — per damaged player for damage to players — so it can too."""
    effects = [e for e in d.get("effects") or []] + [e for m in d.get("modes") or [] for e in m.get("effects") or []]
    wants_player = any(e.get("who") == "event_player" for e in effects)
    wants_amount = any(e.get("n") == {"event_amount": 1} for e in effects)
    if not wants_player and not wants_amount:
        return True
    cond = d.get("cond") if d.get("kind") == "triggered" and d.get("trigger") == "event" else None
    if cond is None:
        return False
    if cond.get("aggregate") and cond["event"] not in _PLAYER_EVENTS:
        return False
    if wants_player and cond.get("subject") != "player" and cond["event"] not in _PLAYER_EVENTS:
        return False
    return not wants_amount or cond["event"] in _AMOUNT_EVENTS


@lru_cache(maxsize=20000)
def _cached(ch: Characteristics) -> dict[int, Definition]:
    out = {}
    for ab in ch.abilities:
        d = define(ab, ch)
        if d is not None and _event_refs_ok(d):
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
    return _cached(replace(ch, pt=None, granted=frozenset(), lost=frozenset(), imposed=frozenset()))


# Combat restrictions and requirements printed on a permanent (CR 508.1c-d, 509.1b-c).
COMBAT_STATICS = {
    "~ can't block.": "cant_block",
    "~ can't attack.": "cant_attack",
    "~ can't attack or block.": "cant_attack_or_block",
    "~ can't be blocked.": "cant_be_blocked",
    "~ attacks each combat if able.": "must_attack",
    "~ can block only creatures with flying.": "block_only_flying",
    "~ can't be blocked by more than one creature.": "max_one_blocker",
    "~ can't attack unless defending player controls an Island.": "attack_needs_island",
    "~ can't be countered.": "cant_be_countered",
    "~ doesn't untap during your untap step.": "doesnt_untap",
    "This spell can't be countered.": "cant_be_countered",
}


# Rules an Aura or Equipment imposes on the object it's attached to (not abilities it grants).
# Each: the restrictions imposed (the names scripts.statics / Characteristics.imposed use).
ATTACHED_RULES: dict[str, tuple[str, ...]] = {
    "can't attack or block.": ("cant_attack_or_block",),
    "can't attack.": ("cant_attack",),
    "can't block.": ("cant_block",),
    "can't be blocked.": ("cant_be_blocked",),
    "attacks each combat if able.": ("must_attack",),
    "doesn't untap during its controller's untap step.": ("doesnt_untap",),
    "can't attack or block, and its activated abilities can't be activated.": ("cant_attack_or_block", "cant_activate"),
    "can't attack or block and its activated abilities can't be activated.": ("cant_attack_or_block", "cant_activate"),
}
# "Enchanted creature's activated abilities can't be activated." (possessive subjects)
_POSSESSIVE_RULES: dict[str, tuple[str, ...]] = {
    "activated abilities can't be activated.": ("cant_activate",),
}


def attached_rule(text: str) -> Definition | None:
    """"Enchanted creature can't attack or block.", "Enchanted creature doesn't untap during its
    controller's untap step." …: a rule for whatever the source is attached to."""
    text = text.replace("’", "'")
    for subject in (*ATTACHED_SUBJECTS, "Enchanted permanent"):
        imposed = None
        if text.startswith(subject + " "):
            imposed = ATTACHED_RULES.get(text[len(subject) + 1:])
        elif text.startswith(subject + "'s "):
            imposed = _POSSESSIVE_RULES.get(text[len(subject) + 3:])
        if imposed is not None:
            return {"kind": "static", "static": "attached_rule", "imposes": list(imposed), "effects": [],
                    "lands": subject == "Enchanted land", "permanent": subject == "Enchanted permanent"}
    return None


def statics(ch: Characteristics) -> set[str]:
    """The combat statics a card has (from its definitions), and those imposed on it by
    attached Auras / Equipment."""
    return {d["static"] for d in definitions(ch).values() if d["kind"] == "static"} | ch.imposed


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
            if kw in ("persist", "undying"):  # 702.79 / 702.93: return with a -1/-1 (+1/+1) counter
                out.append((1000 + ab.index * 10 + k, {
                    "kind": "triggered", "trigger": "dies_self", "optional": False, "target": None,
                    "unless_counter": "-1/-1" if kw == "persist" else "+1/+1",
                    "effects": [{"do": "return_with_counter", "counter": "-1/-1" if kw == "persist" else "+1/+1"}]}))
            f = re.fullmatch(r"fabricate (\d+)", ab.text.strip().rstrip(".").lower()) if kw == "fabricate" else None
            if f:  # 702.123a: "When this permanent enters, put N +1/+1 counters on it or create N 1/1 Servos."
                out.append((1000 + ab.index * 10 + k, {
                    "kind": "triggered", "trigger": "enters_self", "optional": False, "target": None,
                    "effects": [{"do": "fabricate", "n": int(f.group(1))}]}))
            m = re.fullmatch(r"soulshift (\d+)", ab.text.strip().rstrip(".").lower()) if kw == "soulshift" else None
            if m:  # 702.46a: "When this creature dies, you may return target Spirit card with mana value N or less …"
                out.append((1000 + ab.index * 10 + k, {
                    "kind": "triggered", "trigger": "dies_self", "optional": True,
                    "target": {"what": f"graveyard:Spirit:{m.group(1)}"},
                    "effects": [{"do": "bounce", "who": "target"}]}))
    return out


# 700.2: "Choose …" followed by bulleted modes. (n_min, n_max, same mode more than once?, condition)
_MODAL_HEADERS = {
    "Choose one —": (1, 1, False, None),
    "Choose two —": (2, 2, False, None),
    "Choose one or both —": (1, 2, False, None),
    "Choose one or more —": (1, 99, False, None),
    "Choose three. You may choose the same mode more than once.": (3, 3, True, None),
    "Choose one. If you control a commander as you cast this spell, you may choose both instead.": (1, 1, False, "commander"),
}


def modal_definition(lines: list[AbilityText], name: str = "") -> Definition | None:
    """A modal spell (700.2): the header line, then one bulleted line per mode, each an effect
    sentence the engine reads with at most one target. None if any part isn't understood (the
    whole spell is then resolved by hand)."""
    if len(lines) < 3 or lines[0].text not in _MODAL_HEADERS:
        return None
    lo, hi, repeat, condition = _MODAL_HEADERS[lines[0].text]
    modes = []
    for ab in lines[1:]:
        if not ab.text.startswith("• "):
            return None
        parsed = parse_effects(self_text(ab.text[2:], name))
        if parsed is None or parsed[2]:  # ("you may" inside a mode: not yet)
            return None
        effects, target, _ = parsed
        if target is not None and not isinstance(target, str):
            return None  # (a mode with several targets or a division: not yet)
        modes.append({"text": ab.text[2:], "effects": effects, "target": {"what": target} if target else None})
    if not repeat and lo > len(modes):
        return None
    if condition == "commander":  # "… you may choose both instead" (while you control a commander)
        hi = 1
    return {"kind": "spell", "effects": [], "target": None, "modes": modes,
            "modal": {"min": lo, "max": min(hi, 99 if repeat else len(modes)), "repeat": repeat, "condition": condition}}


def spell_definition(ch: Characteristics) -> Definition | None:
    """A whole instant/sorcery as one definition, if every line is automated (else None)."""
    if not ch.is_instant_or_sorcery:
        return None
    text_lines = [ab for ab in ch.abilities if ab.kind != "keywords"]
    if text_lines and text_lines[0].text in _MODAL_HEADERS:
        modal = modal_definition(text_lines, ch.name)
        # (a spell has no trigger event: "that player" / "that much" can't be bound)
        return modal if modal is not None and _event_refs_ok(modal) else None
    defs = definitions(ch)
    lines = [ab for ab in ch.abilities if ab.kind != "keywords"]
    if not lines or any(ab.index not in defs or defs[ab.index]["kind"] != "spell" for ab in lines):
        return None
    # Each line's "target" words are the spell's target groups, in printed order (601.2c, 115.3:
    # "Destroy target creature. / Tap target creature." targets twice, not once).
    groups: list[dict[str, Any]] = []
    effects: list[dict[str, Any]] = []
    for ab in lines:
        own = target_groups(defs[ab.index])
        if groups and any('"other":true' in g["what"] for g in own):
            return None  # ("another target" on a later line: distinct from which target?)
        offset = len(groups)
        index = list(range(offset, offset + len(own)))
        for g in own:
            if g.get("distinct_from"):
                g["distinct_from"] = [offset + d for d in g["distinct_from"]]
            groups.append(g)
        try:
            effects += _renumber(defs[ab.index]["effects"], index)
        except _NoMatch:
            return None
    if any(e.get("who") == "self" for e in effects):
        return None  # ("Exile ~." on an instant or sorcery: the spell itself, which effects don't move)
    effects, target = _finish_targets(effects, groups)
    return {"kind": "spell", "effects": effects, **target_fields(target)}
