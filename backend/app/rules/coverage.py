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
from app.rules.characteristics import HALVES, Characteristics, half_from_data, printed_from_data
from app.rules.mana import parse_mana_ability
from app.rules.oracle import AbilityText

Level = Literal["FULL", "PARTIAL", "REVIEW", "MANUAL"]

# Everything the engine automates today. Add a feature only together with its scenario tests.
SUPPORTED: set[str] = {
    "play:land",  # play_land: timing, one land per turn, priority (M14)
    "cast:spell",  # cast_spell: timing, costs (auto-paid), commander tax, the stack, resolution (M15)
    "mana:ability",  # {T}[, Sacrifice this]: Add … mana abilities, incl. basic land types (M15)
    "combat",  # attacking and blocking, combat damage (M15c)
    # 306/606: loyalty on entering however it enters (306.5b), loyalty abilities (606.3-606.6, incl.
    # −X), damage removing loyalty (120.3c), attacking planeswalkers, 0 loyalty (704.5i):
    # test_rules_loyalty.py, test_rules_combat.py
    "planeswalker",
    # M16: templated Oracle text (app/rules/scripts.py): triggers, spell effects, activated abilities,
    # "enters tapped"; every template has parsing and scenario tests. Static grants ("Other Elves you
    # control get +1/+1 and have haste.", "~ gets +2/+2 as long as …") are app/rules/statics.py, applied
    # in layer order by app/rules/layers.py (test_rules_statics.py).
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
    "changeling", "devoid", "cascade", "persist", "undying", "flanking", "delve", "improvise", "rebound", "storm",
    # costs (casting._convoke_sources)
    "convoke",
    # 702.125 undaunted: costs {1} less for each opponent (permissions.self_reduction)
    "undaunted",
}


# Keyword actions (CR 701) the engine carries out when an ability's text calls for them (a template
# in app/rules/scripts.py over a primitive in app/rules/effects.py or app/rules/keyword_actions.py).
# Coverage of a card is decided by its templates parsing; this set is the honest list for the
# mechanics report (tools/commander_coverage.py). Each entry has scenario tests.
SUPPORTED_KEYWORD_ACTIONS: set[str] = {
    "counter", "create", "destroy", "discard", "exile", "mill", "regenerate", "sacrifice", "scry", "search", "surveil",
    "tap and untap", "proliferate", "investigate", "explore",
    # test_rules_keyword_actions.py
    "amass", "connive", "monstrosity", "bolster", "support",
}


# -- refusals (agent T) ------------------------------------------------------------------------------
# Wordings the grammar reads far enough to know it must NOT automate them, and why. A card with
# one of these stays PARTIAL/MANUAL on purpose; the reason names the missing piece so the gap
# report can rank it (never a guess at what the card does). ``refusal(text)`` gives the reason.
REFUSED: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bfights?\b", re.I),
     "fight (701.14): needs the fight primitive in app/rules/effects.py (the target grammar is ready: language._FIGHTS)"),
    (re.compile(r"\bchoose (?:each of )?(?:up to \w+ |any number of |one or two |\w+ )?(?:(?:an)?other )?targets?\b", re.I),
     "choose_targets: needs a no-op primitive that only names the chosen targets for later sentences "
     "(the target grammar is ready: language._CHOOSE)"),
    (re.compile(r"\bstun counters?\b", re.I), "stun counters (122.1d) aren't modelled (values.UNMODELED_COUNTERS)"),
    (re.compile(r"\bfor each target beyond the first\b", re.I),
     "a cost per extra target (601.2b/601.2c): the cost grammar doesn't read it"),
    (re.compile(r"\btarget (?:player|opponent)'s (?:graveyard|hand|library)\b", re.I),
     "a target player's zone as the object set (\"exile target player's graveyard\"): the effects can't "
     "reach the chosen player from a selector"),
    (re.compile(r"\btarget \w+(?: \w+)* that player controls\b", re.I),
     "a selector relative to a player named earlier (\"target creature that player controls\"): not modelled"),
    (re.compile(r"\bup to x target\b", re.I), "a variable number of targets announced as X (601.2c): not modelled"),
    (re.compile(r"\bcopy target .*abilit", re.I), "copying an ability on the stack (707.10): not modelled"),
    (re.compile(r"\bshuffles? up to \w+ target cards? from their graveyard\b", re.I),
     "cards from a target player's graveyard (a zone bound to an earlier target): not modelled"),
    (re.compile(r"\btarget creature with the greatest\b", re.I), "\"the greatest … among\" (a computed extreme): not modelled"),
    (re.compile(r"\btarget creature's power and toughness\b", re.I), "switching or reading a target's P/T pair: not modelled"),
)


def refusal(text: str) -> str | None:
    """Why the engine refuses to automate this wording, if it is a known refusal (else None)."""
    for pattern, reason in REFUSED:
        if pattern.search(text):
            return reason
    return None


# Cycling / typecycling with a plain mana cost (casting.cycle); "Cycling—Pay 2 life" and friends stay manual.
_MANA_CYCLING = re.compile(r"(?:(?:basic )?[a-z]+)?cycling (?:\{[^}]+\})+")


_MANA_FLASHBACK = re.compile(r"flashback (?:\{[^}]+\})+")


# 702.124a: partner abilities modify deck construction and "function before the game begins":
# during the game there's nothing to do (pairings are checked by app/rules/commander.py and the
# deck checks). "Partner with [name]" also has an enters trigger (702.124j): not listed here.
DECKBUILDING_KEYWORDS = {"partner", "choose a background", "doctor's companion", "friends forever"}


def _keyword_supported(kw: str, line: str) -> bool:
    if kw in DECKBUILDING_KEYWORDS:
        return not line.strip().lower().startswith("partner with")
    if kw in ("enchant", "equip"):  # app/rules/attachments.py: the wordings it maps
        from app.rules import attachments

        return attachments.supported_keyword(kw, line)
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
    if kw in ("bushido", "renown", "bloodthirst", "soulshift", "toxic", "fabricate"):  # numbered keywords (triggers.py, engine.enter_with_counters)
        return re.fullmatch(rf"{kw} \d+", line.strip().rstrip(".").lower()) is not None
    if kw == "suspend":  # casting.suspend_info: "Suspend N—{cost}"
        return re.fullmatch(r"suspend \d+\s*[—-]\s*(?:\{[^}]+\})+", line.strip().rstrip(".").lower()) is not None
    if kw == "cumulative upkeep":  # triggers.cumulative_cost: a mana cost
        return re.fullmatch(r"cumulative upkeep (?:\{[^}]+\})+", line.strip().rstrip(".").lower()) is not None
    if kw in ("unearth", "dash", "buyback", "madness", "ward", "evoke"):  # casting.keyword_cost: a mana cost
        return re.fullmatch(rf"{kw} (?:\{{[^}}]+\}})+", line.strip().rstrip(".").lower()) is not None
    if kw in ("kicker", "multikicker"):  # casting.cost_with_kicker: one mana kicker cost
        from app.rules.costs import kicker_line

        return kicker_line(line)
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
    if ch.is_instant_or_sorcery:
        whole = templates.spell_definition(ch)
        if whole is None:
            templated = set()  # a spell is automated as a whole or resolved by hand
        elif whole.get("modes"):
            templated = {ab.index for ab in ch.abilities if ab.kind != "keywords"}  # a modal spell (700.2)
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
    if len(faces) > 1:  # double-faced, split, adventure, flip …: each face's text on its own (no "//" line)
        halves = data.get("layout") in HALVES  # split cards / adventures: each half is its own spell
        parts = [of_characteristics(half_from_data(data, i) if halves else printed_from_data(data, i))
                 for i in range(len(faces))]
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
