"""-- ability words (wave 9C) -- "Until end of turn, creatures you control gain trample and get +1/+1 for each basic land type
among lands you control." (Tromp the Domains), "Until end of turn, target creature gets +1/+1 for each creature you control
and gains trample." (Chorus of Might, Get a Leg Up, King Harald's Revenge), "{3}{G}: Until end of turn, this creature gets
+1/+1 for each …" (Sunbathing Rootwalla), "… gains indestructible and gets +1/+1 for each …" (Ursine Monstrosity).

One duration ("until end of turn", 611.2a) says how long every part of the sentence lasts, wherever it is written; a pump
that depends on a count is read as the count is when the effect begins and does not change (611.2c: a continuous effect
from a resolving spell or ability that modifies characteristics locks in its set of affected objects and, for a count,
the number is determined as it begins: 608.2h). The sentence is read as the same instructions in the order the grammar
already reads: "[subject] gets +a/+b until end of turn for each [count]. [It / the subject] gains [keywords] until end of
turn." (A second sentence names a target by "it": the one target, 608.2b.) Anything with another shape stays as written.
"""

from __future__ import annotations

import re

_PT = r"[+-]\d+/[+-]\d+"
_UNTIL = " until end of turn"
_PUMP_FIRST = re.compile(rf"^(?P<lead>Until end of turn, )?(?P<subj>[^,.]+?) gets (?P<pt>{_PT})(?P<d1>{_UNTIL})? for each "
                         rf"(?P<cnt>[^,.]+?)(?: and gains (?P<kw>[a-z ]+?))?(?P<d2>{_UNTIL})?$")
_GAIN_FIRST = re.compile(rf"^(?P<lead>Until end of turn, )?(?P<subj>[^,.]+?) gains? (?P<kw>[a-z ]+?)(?P<d1>{_UNTIL})? and gets? "
                         rf"(?P<pt>{_PT})(?P<d2>{_UNTIL})? for each (?P<cnt>[^,.]+?)$")
_SINGULAR = re.compile(r"^(?:target |up to one target |this |~$)")


def _keywords(text: str) -> list[str] | None:
    from app.rules.statics import GRANTABLE_KEYWORDS

    words = [w.strip() for w in re.split(r",\s*(?:and\s+)?|\s+and\s+", text) if w.strip()]
    return words if words and all(w in GRANTABLE_KEYWORDS for w in words) else None


def _sentence(text: str) -> str | None:
    m = _PUMP_FIRST.match(text)
    pump_first = m is not None
    if m is None:
        m = _GAIN_FIRST.match(text)
    if m is None:
        return None
    marks = [bool(m["lead"]), bool(m["d1"]), bool(m["d2"])]
    if sum(marks) != 1:
        return None  # (one duration, written once: otherwise the sentence says something else)
    subj, kw = m["subj"], m.group("kw")
    keywords = _keywords(kw) if kw else []
    if keywords is None:
        return None
    cap = subj[:1].upper() + subj[1:]
    plural = not _SINGULAR.match(subj)
    it = "They" if plural else "It"
    targeted = subj.startswith(("target ", "up to one target "))
    again = it if targeted else cap  # (a second sentence about a target says "it": a new "target" would be a new target, 115.3)
    pump_verb, gain_verb = ("get", "gain") if plural else ("gets", "gains")

    def pump(who: str) -> str:
        return f"{who} {pump_verb} {m['pt']}{_UNTIL} for each {m['cnt']}."

    def gain(who: str) -> str:
        return f"{who} {gain_verb} {' and '.join(keywords)}{_UNTIL}."

    if not keywords:
        return pump(cap)
    return f"{pump(cap)} {gain(again)}" if pump_first else f"{gain(cap)} {pump(again)}"


def rewrite(body: str) -> str:
    """The body with each such sentence worded as the instructions the grammar reads (others unchanged)."""
    from app.rules.oracle import split_sentences

    sentences = split_sentences(body)
    out, changed = [], False
    for s in sentences:
        new = _sentence(s.rstrip(".")) if s.endswith(".") and '"' not in s else None
        changed = changed or new is not None
        out.append(new or s)
    return " ".join(out) if changed else body
