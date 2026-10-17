"""Card analysis: Oracle text → rules features and normalised templates (data only).

Each ability line of each face becomes a ``Segment`` with a rules-feature kind (keyword,
triggered, activated, mana, static, replacement, prevention, permission, restriction, cost
modifier, characteristic-defining, spell effect …) and a **template**: the text with the card's
name, numbers, mana symbols and quoted text abstracted, so "When ~ enters, draw N card(s)." is one
template shared by hundreds of cards. Templates are what the engine implements once and reuses;
the coverage tools rank the missing ones by how many Commander-legal cards they would unlock.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.rules.oracle import parse_abilities

FeatureKind = str

# Keyword actions (CR 701) that appear inside effects. The research tool checks this list against
# the current rules (tools/commander_coverage.py reports any 701 heading not listed here).
KEYWORD_ACTIONS = (
    "activate", "attach", "cast", "counter", "create", "destroy", "discard", "double", "triple", "exchange", "exile",
    "fight", "goad", "investigate", "mill", "play", "regenerate", "reveal", "sacrifice", "scry", "search", "shuffle",
    "surveil", "tap", "untap", "fateseal", "clash", "planeswalk", "set in motion", "abandon", "proliferate",
    "transform", "detain", "populate", "monstrosity", "vote", "bolster", "manifest", "support", "meld", "explore",
    "assemble", "adapt", "amass", "learn", "venture into the dungeon", "connive", "open an attraction",
    "roll to visit your attractions", "convert", "incubate", "the ring tempts you", "face a villainous choice",
    "time travel", "discover", "cloak", "collect evidence", "suspect", "forage", "manifest dread", "endure",
    "harness", "airbend", "earthbend", "waterbend",
)

_NUMBER_WORDS = r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|twenty|X)\b"
_QUOTED = re.compile(r"“[^”]*”|\"[^\"]*\"")


def template(text: str, name: str) -> str:
    """Normalise an ability for grouping: the card's own name → ~, numbers → N, mana → {M}."""
    t = text
    for n in sorted({name, name.split(",")[0].strip(), name.split(" ")[0]}, key=len, reverse=True):
        if len(n) >= 3:
            t = re.sub(rf"\b{re.escape(n)}\b", "~", t)
    t = re.sub(r"\b[Tt]his (creature|artifact|enchantment|land|permanent|card|spell|Equipment|Aura|Vehicle)\b", "~", t)
    t = _QUOTED.sub("“…”", t)
    t = re.sub(r"\{[^}]+\}", "{M}", t)
    t = re.sub(r"(\{M\})+", "{M}", t)
    t = re.sub(r"[+−-]\d+/[+−-]\d+", "±N/±N", t)
    t = re.sub(r"\b\d+/\d+\b", "N/N", t)
    t = re.sub(r"\b\d+\b", "N", t)
    t = re.sub(_NUMBER_WORDS, "N", t)
    t = re.sub(r"\bN (card|creature|token|counter|land|permanent|life)s?\b", r"N \1(s)", t)
    t = re.sub(r"\ba (card|creature|token|counter|land|permanent)\b", r"N \1(s)", t)
    return t.strip()


def feature_kind(ability_kind: str, text: str) -> FeatureKind:
    low = text.lower()
    if ability_kind in ("keywords", "mana", "triggered", "activated", "loyalty"):
        return {"keywords": "keyword", "mana": "mana_ability", "triggered": "triggered", "activated": "activated",
                "loyalty": "loyalty"}[ability_kind]
    if re.search(r"\bwould\b.*\binstead\b", low) or re.search(r"\benters (the battlefield )?(tapped|with)\b", low) \
            or low.startswith("as ~ enters") or "as this" in low and "enters" in low:
        return "replacement"
    if "prevent" in low:
        return "prevention"
    if re.search(r"\byou may (cast|play)\b.*\bfrom\b", low) or "you may cast" in low and "from" in low:
        return "permission"
    if re.search(r"\bcosts? \{m\}|\bcost \{[^}]+\} (less|more)|\bcosts? (\w+ )?(less|more) to cast\b", low):
        return "cost_modifier"
    if re.search(r"\brather than pay\b|\bwithout paying\b", low):
        return "alternative_cost"
    if low.startswith("as an additional cost"):
        return "additional_cost"
    if re.search(r"\b(power|toughness)( and toughness)? (is|are) (each )?equal to\b|\bis (all colors|every creature type)\b", low):
        return "characteristic_defining"
    if re.search(r"\bcan't\b|\bcan’t\b|\bdoesn't untap\b|\bdoesn’t untap\b|\bonly\b.*\bcan\b", low):
        return "restriction"
    if ability_kind == "spell":
        return "spell_effect"
    if re.search(r"\b(get|gets|have|has|gain|gains|lose|loses)\b", low):
        return "continuous"
    return "static"


def keyword_actions_in(text: str) -> list[str]:
    low = text.lower()
    return [a for a in KEYWORD_ACTIONS if re.search(rf"\b{re.escape(a)}(s|es|ed|ing)?\b", low)]


@dataclass(frozen=True)
class Segment:
    face: int
    index: int
    text: str
    kind: FeatureKind
    template: str
    keywords: tuple[str, ...] = ()
    actions: tuple[str, ...] = ()


def segments(data: dict[str, Any]) -> list[Segment]:
    """Every ability line of every face (a double-faced or split card has both halves)."""
    faces = data.get("faces") or data.get("card_faces") or []
    parts = faces if faces else [data]
    out: list[Segment] = []
    for i, part in enumerate(parts):
        type_line = str(part.get("type_line") or data.get("type_line") or "")
        spell = bool(re.search(r"\b(Instant|Sorcery)\b", type_line))
        name = str(part.get("name") or data.get("name") or "")
        for ab in parse_abilities(part.get("oracle_text"), spell=spell, pt=(part.get("power"), part.get("toughness"))):
            out.append(Segment(face=i, index=ab.index, text=ab.text, kind=feature_kind(ab.kind, ab.text),
                               template=template(ab.text, name), keywords=ab.keywords,
                               actions=tuple(keyword_actions_in(ab.text)) if ab.kind != "keywords" else ()))
    return out
