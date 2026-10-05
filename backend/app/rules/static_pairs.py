"""-- as long as (wave 9B) -- statics worded over several sentences, researched against CR 2026-09-25.

"Enchanted creature gets +2/+1 as long as it's black. Otherwise, it gets -1/-2." (Phyrexian Boon), "Equipped creature gets +1/+0. It
gets +3/+1 instead as long as an opponent has eight or more cards in their graveyard." (Mind Carver), "Equipped creature gets
+1/+1. As long as it's legendary, it gets an additional +2/+2. As long as it's red, it has trample." (Tenza, Godo's Maul), "As long as
your life total is greater than your starting life total, ~ gets +1/+1 and has menace. ~ gets an additional +5/+5 as long as …"
(Elenda, Saint of Dusk).

Each sentence is a static ability of the same object (604.1), and each is a continuous effect that applies at any moment its own
condition is true (611.3a, 604.2): "Otherwise" and "instead" make two conditions that exclude each other, "an additional" adds to the
other effects (613.4c: all the +N/+N changes apply). So the ability is a set of the ordinary conditional statics (app/rules/statics.py)
that apply together: the first is the definition and the rest are its ``also`` list (app/rules/layers.py reads them as statics of the
same permanent with the same timestamp). A sentence the single-sentence grammar doesn't read leaves the whole ability manual.

"It" in a later sentence is the object the first sentence is about: the enchanted / equipped creature, or the permanent itself.
"""

from __future__ import annotations

import re
from typing import Any

Definition = dict[str, Any]

_SENTENCES = re.compile(r"(?<=\.) (?=[A-Z~])")
_SUBJECT = re.compile(r"^(?:As long as [^,]+, )?(?P<s>Enchanted creature|Equipped creature|~)(?= (?:gets|has|can't)\b)")
_OTHERWISE = re.compile(r"^Otherwise, it (?P<pred>(?:gets|has|can't) .+)\.$")  # (wave 25A: "it can't attack or block", Bonds of Faith)
_INSTEAD = re.compile(r"^(?:It|~) (?P<pred>(?:gets|has) .+?) instead as long as (?P<cond>.+)\.$")


def _not(conds: list[dict[str, Any]]) -> dict[str, Any]:
    return {"static": "not", "cond": conds[0] if len(conds) == 1 else {"static": "all", "conds": conds}}


def definition(text: str) -> Definition | None:
    from app.rules import statics

    # -- as long as (wave 25A) -- "As long as you control enchanted creature, it gets +2/+2.": "it" is the creature the condition names
    text = re.sub(r"^(As long as [^,]*\b(enchanted|equipped) creature\b[^,]*), it (?=(?:gets|has|can't)\b)",
                  lambda m: f"{m[1]}, {m[2].capitalize()} creature ", text.strip())
    from app.rules import abilities_of  # -- keyword inheritance (wave 25A) -- "The same is true for …"

    if (inherited := abilities_of.inherit(text, statics._definition)) is not None:
        return inherited
    parts = _SENTENCES.split(text.strip())
    if not 2 <= len(parts) <= 3:
        return None
    head = _SUBJECT.match(parts[0])
    if head is None:
        # "As long as C, ~ gets …" (the subject follows the condition) or a sentence of another shape
        head = re.match(r"^As long as .+?, (?P<s>~)(?= (?:gets|has)\b)", parts[0])
        if head is None:
            return None
    subject = head["s"]
    attached = subject != "~"
    low = subject.lower()

    def plain(sentence: str) -> str:
        sentence = re.sub(r"\bgets an additional\b", "gets", sentence)  # (613.4c: it adds to the other changes)
        if attached:
            sentence = re.sub(r"\bas long as it's\b", f"as long as {low} is", sentence)
            sentence = re.sub(r"\bAs long as it's\b", f"As long as {low} is", sentence)
        return sentence

    defs: list[Definition] = []
    for i, sentence in enumerate(parts):
        other, instead = _OTHERWISE.match(sentence), _INSTEAD.match(sentence)
        if i == 0 and (other or instead):
            return None
        if other:
            before = defs[-1]
            if not before["conditions"] or before.get("also"):
                return None  # ("Otherwise" says what happens when the sentence before it doesn't)
            # (-- as long as (wave 20B) -- "~ has hexproof." alone is a keyword line, not a static: a stand-in condition, replaced below)
            d = statics.parse(f"{subject} {other['pred']}." if attached else f"As long as it's your turn, ~ {other['pred']}.")
            if d is None or (attached and d["conditions"]):
                return None
            d["conditions"] = [_not(before["conditions"])]
        elif instead:
            d = statics.parse(plain(f"{subject} {instead['pred']} as long as {instead['cond']}."))
            if d is None or not d["conditions"] or not defs or defs[-1]["conditions"]:
                return None  # ("instead" replaces an unconditional sentence before it)
            defs[-1]["conditions"] = [_not(d["conditions"])]
        else:
            d = statics.parse(plain(sentence))
            if d is None:
                return None
        if d["who"] != ("attached" if attached else "self") or (attached and d.get("attached_kind") != "creature"):
            return None
        defs.append(d)
    first = dict(defs[0])
    first["also"] = defs[1:]
    return first
