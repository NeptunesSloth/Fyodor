"""-- activated sweep (wave 26C) -- one subject, several predicates: "This creature gets +3/+3 and becomes a Bear Berserker until end of
turn." (Ursine Champion), "Until end of turn, this creature becomes a Dragon, gets +5/+3, and gains flying and trample." (Dragonsoul
Knight), "This creature loses defender and becomes a Human until end of turn." (Wishful Merfolk).

CR 2026-09-25: 611.2a / 613.1: a continuous effect of one resolving sentence is made once, but each of its parts changes one characteristic in
its own layer (type 4, abilities 6, power and toughness 7c), so the parts are the same effects the sentence would give if each were said alone
("gets +3/+3 until end of turn", "becomes a Bear Berserker until end of turn") made at the same time, in the order written (608.2c). The
sentence is split into those sentences when the grammar doesn't read it as it is (scripts.parse_effects asks only then). Only a subject that is
the source itself (the same object in every part; a target would be a second target) and a lasting effect with one duration are split."""

from __future__ import annotations

import re

_VERB = r"(?:gets?|gains?|loses?|becomes?|has)"
_SPLIT = re.compile(rf"(?:, and |, | and )(?={_VERB} )")
_SENTENCE = re.compile(
    r"^(?P<lead>Until end of turn, )?(?P<s>[Tt]his (?:creature|land|artifact|permanent|Equipment|Vehicle)|~) (?P<preds>.+?)"
    r"(?P<trail> until end of turn)?\.?$")


def split(body: str) -> str | None:
    """``body`` with each such sentence written as one sentence for each predicate, or None when no sentence is one."""
    parts = re.split(r"(?<=\.) (?=[A-Z~])", body.strip())
    changed = False
    out: list[str] = []
    for sentence in parts:
        m = _SENTENCE.match(sentence) if '"' not in sentence else None
        if m is None or bool(m["lead"]) == bool(m["trail"]):
            out.append(sentence)
            continue
        preds = _SPLIT.split(m["preds"])
        if len(preds) < 2 or not any(p.startswith(("becomes", "become")) for p in preds) \
                or any(not re.match(rf"{_VERB} ", p) for p in preds):
            out.append(sentence)
            continue
        subject = m["s"]
        out += [f"{m['lead'] or ''}{subject if m['lead'] else subject[0].upper() + subject[1:]} {p}{m['trail'] or ''}." for p in preds]
        changed = True
    return " ".join(out) if changed else None
