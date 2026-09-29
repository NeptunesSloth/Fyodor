"""Cluster what the engine can't do yet into reusable capabilities (for the coverage report).

A missing ability line is classified by WHY it isn't automated, so one implementation unlocks a
whole cluster instead of one card:

* MISSING MECHANIC — a keyword (CR 702) the engine doesn't implement (or a wording of one);
* MISSING TRIGGER EVENT — "When/Whenever/At …" whose event isn't recognised;
* MISSING SELECTOR — the effect names a target ("target creature with flying") we can't select;
* MISSING EFFECT — the trigger/cost/target are fine but the effect wording isn't recognised;
* MISSING COST — an activated ability's cost isn't understood;
* MISSING REPLACEMENT PATTERN — "enters tapped unless …", "If … would …, instead …", prevention;
* MISSING CONTINUOUS EFFECT / RESTRICTION / COST RULE — static abilities by family;
* MANA ABILITY WORDING — a mana ability the mana parser doesn't read;
* UNSUPPORTED ORACLE PATTERN — anything else.

This is analysis only (heuristics over Oracle text); it never decides what the engine does.
"""

from __future__ import annotations

import re

from app.rules import analysis, scripts
from app.rules.costs import parse_ability_cost

MECHANIC = "MISSING MECHANIC"
TRIGGER = "MISSING TRIGGER EVENT"
SELECTOR = "MISSING SELECTOR"
EFFECT = "MISSING EFFECT"
COST = "MISSING COST"
REPLACEMENT = "MISSING REPLACEMENT PATTERN"
CONTINUOUS = "MISSING CONTINUOUS EFFECT"
RESTRICTION = "MISSING RESTRICTION"
COST_RULE = "MISSING COST / PERMISSION RULE"
MANA = "MANA ABILITY WORDING"
OTHER = "UNSUPPORTED ORACLE PATTERN"
CATEGORIES = (MECHANIC, EFFECT, SELECTOR, TRIGGER, REPLACEMENT, CONTINUOUS, RESTRICTION, COST, COST_RULE, MANA, OTHER)

_SELECTOR_KEYS = sorted(scripts.SELECTORS, key=len, reverse=True)
_TARGET = re.compile(r"\btarget\b")
_STOP = re.compile(r"[,.;:]| (?:gets?|gains?|loses?|deals?|and|to|from|with(?:out)? power|that|you|can't|on|into|"
                   r"is|are|has|have|becomes?|unless|until|this|for|each|attacks|blocks|dies)\b")
_CUT = re.compile(r"\b(unless|if|as long as|except|where|for each)\b|,")


def _family(template: str, words: int = 7) -> str:
    """A pattern family: the template up to its condition ("~ enters tapped unless …")."""
    m = _CUT.search(template)
    head = template[: m.end()] if m and m.start() > 0 else template
    toks = head.rstrip(".").split()
    fam = " ".join(toks[:words])
    return fam + (" …" if len(toks) > words or fam != template.rstrip(".") else "")


def missing_selector(text: str) -> str | None:
    """A "target …" phrase none of the engine's selectors reads, or None."""
    low = text.lower()
    for m in _TARGET.finditer(low):
        rest = low[m.start():]
        if any(rest.startswith(k) and (len(rest) == len(k) or _STOP.match(rest, len(k))) for k in _SELECTOR_KEYS):
            continue  # a selector we read, followed by the rest of the sentence
        stop = _STOP.search(rest, len("target"))
        phrase = rest[: stop.start()] if stop else rest
        return analysis.template(" ".join(phrase.split()[:6]), "")
    return None


def _effect(body: str, name: str) -> tuple[str, str]:
    sel = missing_selector(body)
    if sel:
        return SELECTOR, sel
    first = re.split(r"(?<=\.)\s+", body.strip())[0]
    t = analysis.template(first, name).rstrip(".")
    t = re.sub(r"^(?:you may|then|if you do,?)\s+", "", t, flags=re.IGNORECASE)
    words = []
    for w in t.split():
        if w in ("N", "{M}", "~", "“…”") or w.startswith("target") or w.endswith(","):
            words.append(w.rstrip(","))
            if len(words) >= 2:
                break
            continue
        words.append(w)
        if len(words) >= 4:
            break
    return EFFECT, " ".join(words).lower() + " …"


def _trigger_understood(text: str) -> bool:
    """Is the trigger condition read (a specific template, or the generic condition grammar)?"""
    from app.rules import events

    for pattern, name in scripts.TRIGGERS:
        m = pattern.match(text)
        if m:
            return name != "event" or events.parse_condition(m["cond"]) is not None
    return False


def classify(feature_id: str, label: str, kind: str, name: str) -> tuple[str, str]:
    """(category, cluster) for one missing feature of a card."""
    if feature_id.startswith("keyword:"):
        return MECHANIC, feature_id.split(":", 1)[1]
    if feature_id == "mana:ability":
        return MANA, _family(analysis.template(label, name), 6)
    if not feature_id.startswith("text:"):
        return OTHER, feature_id
    text = scripts.self_text(label, name)
    tmpl = analysis.template(label, name)
    if kind == "triggered":
        if not _trigger_understood(text):
            cond = tmpl.split(",")[0]
            return TRIGGER, analysis.template(cond, name)
        return _effect(text.split(", ", 1)[1] if ", " in text else text, name)
    if kind in ("activated", "loyalty"):
        cost, _, body = text.partition(":")
        if kind == "activated" and parse_ability_cost(cost, card_name=name).unsupported:
            return COST, analysis.template(cost, name)
        return _effect(body, name)
    if kind == "spell_effect":
        return _effect(text, name)
    if kind in ("replacement", "prevention"):
        return REPLACEMENT, _family(tmpl)
    if kind in ("continuous", "characteristic_defining"):
        sel = missing_selector(text)
        return (SELECTOR, sel) if sel else (CONTINUOUS, _family(tmpl, 6))
    if kind == "restriction":
        return RESTRICTION, _family(tmpl, 6)
    if kind in ("cost_modifier", "alternative_cost", "additional_cost", "permission"):
        return COST_RULE, _family(tmpl, 6)
    return OTHER, _family(tmpl, 6)
