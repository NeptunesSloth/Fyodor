"""How much of a card the rules engine automates: FULL / PARTIAL / REVIEW / MANUAL.

A card is broken into *features*: what it needs to be played (a land drop, casting a spell,
fighting in combat) and one feature per ability line (a keyword, a mana ability, a scripted
ability, or free text). Coverage compares those features with ``SUPPORTED``, the set of things
the engine really implements. ``SUPPORTED`` only grows when a feature lands *with* tests, so the
report is honest: a card is FULL only when every part of it is automated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.rules import cards as scripts
from app.rules import protection
from app.rules import scripts as templates
from app.rules.characteristics import Characteristics, printed_from_data
from app.rules.mana import parse_mana_ability
from app.rules.oracle import AbilityText

Level = Literal["FULL", "PARTIAL", "REVIEW", "MANUAL"]

# Everything the engine automates today. Add a feature only together with its scenario tests.
SUPPORTED: set[str] = {
    "play:land",  # play_land: timing, one land per turn, priority (M14)
    "cast:spell",  # cast_spell: timing, costs (auto-paid), commander tax, the stack, resolution (M15)
    "mana:ability",  # {T}[, Sacrifice this]: Add … mana abilities, incl. basic land types (M15)
    "combat",  # attacking and blocking, combat damage (M15c)
    # M16: templated Oracle text (app/rules/scripts.py): triggers, spell effects, activated abilities,
    # "enters tapped"; every template has parsing and scenario tests.
    "templates",
}

# Keyword abilities the engine implements (each needs tests before it is listed here).
SUPPORTED_KEYWORDS: set[str] = {
    # combat (M15c): legality and damage, each covered by test_rules_combat.py
    "flying", "reach", "vigilance", "trample", "deathtouch", "lifelink", "first strike", "double strike",
    "haste", "defender", "menace",
    # state-based actions (M15b)
    "indestructible",
    # M16: casting timing and targeting (test_rules_effects.py)
    "flash", "hexproof", "shroud",
    # evasion (test_rules_combat.py::test_evasion, landwalk tests)
    "plainswalk", "islandwalk", "swampwalk", "mountainwalk", "forestwalk", "desertwalk",
    "shadow", "horsemanship", "fear", "intimidate", "skulk",
    # triggered keywords (app/rules/scripts.py KEYWORD_TRIGGERS)
    "prowess",
    # damage as counters (test_rules_infect.py)
    "wither", "infect",
    # exalted (app/rules/triggers.py _exalted, test_rules_infect.py)
    "exalted",
    # characteristic-defining (app/rules/characteristics.py changeling)
    "changeling", "devoid", "cascade",
    # costs (casting._convoke_sources)
    "convoke",
}


# Cycling / typecycling with a plain mana cost (casting.cycle); "Cycling—Pay 2 life" and friends stay manual.
_MANA_CYCLING = re.compile(r"(?:(?:basic )?[a-z]+)?cycling (?:\{[^}]+\})+")


_MANA_FLASHBACK = re.compile(r"flashback (?:\{[^}]+\})+")


def _keyword_supported(kw: str, line: str) -> bool:
    if kw == "protection":  # DEBT for the qualities app/rules/protection.py understands
        return protection.supported(line)
    if kw == "affinity":  # casting.affinity_filter
        from app.rules.casting import affinity_filter  # casting imports coverage (via engine)

        return affinity_filter(Characteristics(name="", abilities=(AbilityText(index=0, text=line, kind="keywords",
                                                                              keywords=("affinity",)),))) is not None
    if kw == "echo":  # triggers.echo_cost: a mana echo cost
        return re.fullmatch(r"echo (?:\{[^}]+\})+", line.strip().rstrip(".").lower()) is not None
    if kw in ("morph", "megamorph"):  # casting.morph_cost: a mana morph cost
        return re.fullmatch(r"(?:mega)?morph (?:\{[^}]+\})+", line.strip().rstrip(".").lower()) is not None
    if kw in ("bushido", "renown", "bloodthirst"):  # numbered keywords (triggers.py, engine.enter_with_counters)
        return re.fullmatch(rf"{kw} \d+", line.strip().rstrip(".").lower()) is not None
    if kw == "suspend":  # casting.suspend_info: "Suspend N—{cost}"
        return re.fullmatch(r"suspend \d+\s*[—-]\s*(?:\{[^}]+\})+", line.strip().rstrip(".").lower()) is not None
    if kw == "cumulative upkeep":  # triggers.cumulative_cost: a mana cost
        return re.fullmatch(r"cumulative upkeep (?:\{[^}]+\})+", line.strip().rstrip(".").lower()) is not None
    if kw in ("unearth", "dash", "buyback", "madness", "ward"):  # casting.keyword_cost: a mana cost
        return re.fullmatch(rf"{kw} (?:\{{[^}}]+\}})+", line.strip().rstrip(".").lower()) is not None
    if kw == "crew":  # casting.crew: "Crew N"
        return re.fullmatch(r"crew \d+", line.strip().rstrip(".").lower()) is not None
    if kw == "flashback":  # casting.flashback_cost: a mana flashback cost
        return _MANA_FLASHBACK.fullmatch(line.strip().rstrip(".").lower()) is not None
    if kw.endswith("cycling"):
        return _MANA_CYCLING.fullmatch(line.strip().rstrip(".").lower()) is not None
    return kw in SUPPORTED_KEYWORDS


@dataclass(frozen=True)
class Feature:
    id: str  # e.g. "play:land", "cast:spell", "combat", "keyword:flying", "mana:intrinsic", "text:2"
    label: str  # human readable ("Flying", "{T}: Add {G}.", "Play as a land")
    supported: bool


@dataclass(frozen=True)
class Coverage:
    level: Level
    name: str
    oracle_id: str | None
    features: tuple[Feature, ...] = field(default_factory=tuple)
    review_needed: bool = False  # a script exists but the Oracle text changed since it was validated

    @property
    def manual_parts(self) -> list[str]:
        return [f.label for f in self.features if not f.supported]

    def as_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "name": self.name,
            "oracle_id": self.oracle_id,
            "features": [{"id": f.id, "label": f.label, "supported": f.supported} for f in self.features],
            "manual_parts": self.manual_parts,
            "review_needed": self.review_needed,
        }


def features_of(ch: Characteristics) -> list[Feature]:
    script = scripts.trusted(ch.oracle_id, ch.oracle_text)
    templated = set(templates.definitions(ch))
    if ch.is_instant_or_sorcery and templates.spell_definition(ch) is None:
        templated = set()  # a spell is automated as a whole or resolved by hand
    out: list[Feature] = []

    def add(fid: str, label: str, ok: bool | None = None) -> None:
        out.append(Feature(fid, label, fid in SUPPORTED if ok is None else ok))

    if ch.is_land:
        add("play:land", "Play it as your land for the turn")
    elif ch.types:
        add("cast:spell", "Cast it (timing, costs, the stack)")
    if ch.is_creature:
        add("combat", "Attack and block")
    if "Planeswalker" in ch.types:
        add("planeswalker", "Loyalty and damage to planeswalkers")
    for ab in ch.abilities:
        if script is not None and ab.index in script.covers:
            add(f"script:{ab.index}", ab.text, True)
        elif ab.kind == "keywords":
            for kw in ab.keywords:
                add(f"keyword:{kw}", kw.capitalize(), _keyword_supported(kw, ab.text))
        elif ab.kind == "mana":
            add("mana:ability", ab.text, "mana:ability" in SUPPORTED and parse_mana_ability(ab.text) is not None)
        else:
            add(f"text:{ab.index}", ab.text, ab.index in templated)
    return out


def of_characteristics(ch: Characteristics) -> Coverage:
    feats = tuple(features_of(ch))
    supported = sum(1 for f in feats if f.supported)
    if feats and supported == len(feats):
        level: Level = "FULL"
    elif supported:
        level = "PARTIAL"
    else:
        level = "MANUAL"
    stale = scripts.get(ch.oracle_id) is not None and scripts.trusted(ch.oracle_id, ch.oracle_text) is None
    if stale:
        level = "REVIEW"  # a script exists, but for different Oracle text: never claim FULL on a guess
    return Coverage(level=level, name=ch.name, oracle_id=ch.oracle_id, features=feats, review_needed=stale)


def of_card_data(data: dict[str, Any]) -> Coverage:
    """Coverage of a card from the card database (all faces of a double-faced card count)."""
    faces = data.get("faces") or []
    if data.get("layout") in ("transform", "modal_dfc") and len(faces) > 1:
        parts = [of_characteristics(printed_from_data(data, i)) for i in range(len(faces))]
        feats = tuple(f for p in parts for f in p.features)
        supported = sum(1 for f in feats if f.supported)
        level: Level = "FULL" if supported == len(feats) and feats else ("PARTIAL" if supported else "MANUAL")
        review = any(p.review_needed for p in parts)
        if review:
            level = "REVIEW"
        return Coverage(level=level, name=str(data.get("name") or ""), oracle_id=data.get("oracle_id"), features=feats,
                        review_needed=review)
    return of_characteristics(printed_from_data(data, 0))


def ability_supported(ch: Characteristics, index: int) -> bool:
    """Whether the engine can carry out ability ``index`` of this object by itself."""
    script = scripts.trusted(ch.oracle_id, ch.oracle_text)  # a script for other Oracle text: by hand
    if script is not None and index in script.covers:
        return True
    ab = next((a for a in ch.abilities if a.index == index), None)
    if ab is None:
        return False
    if ab.kind == "keywords":
        return all(k in SUPPORTED_KEYWORDS for k in ab.keywords)
    if ab.kind == "mana":
        return "mana:ability" in SUPPORTED and parse_mana_ability(ab.text) is not None
    if ch.is_instant_or_sorcery:
        return templates.spell_definition(ch) is not None
    return index in templates.definitions(ch)
