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


def parts(definition: Definition) -> tuple[Definition, ...]:
    """Independent statics belonging to the same printed ability index."""
    return (definition, *(part for child in definition.get('also', ()) for part in parts(child)))

_SENTENCES = re.compile(r"(?<=\.) (?=[A-Z~])")
_SUBJECT = re.compile(r"^(?:As long as [^,]+, )?(?P<s>Enchanted creature|Equipped creature|~)(?= (?:gets|has|can't)\b)")
_OTHERWISE = re.compile(r"^Otherwise, it (?P<pred>(?:gets|has|can't) .+)\.$")  # (wave 25A: "it can't attack or block", Bonds of Faith)
_INSTEAD = re.compile(r"^(?:It|~) (?P<pred>(?:gets|has) .+?) instead as long as (?P<cond>.+)\.$")


# "Equipped creature has lifelink if you control a Cleric, deathtouch if you control a Rogue, haste if you control a Warrior, and flying if you control a Wizard." (Multiclass
# Baldric), "Each creature you control has vigilance if it's white, hexproof if it's blue, lifelink if it's black, first strike if it's red, and trample if it's green." (Scion of
# Draco): each part is a grant of its own that applies while its condition is true (611.3a, 604.2): "has lifelink as long as you control a Cleric" / "that's white has vigilance"
_KW_IFS = re.compile(r"^(?P<s>(?:Equipped|Enchanted) creature|Each creature you control) has (?P<list>(?:[a-z]+(?: strike)? if (?:you control an? [A-Z][a-z]+|it's (?:white|blue|black|red|green))"
                     r"(?:, and |, |))+)\.$")
_KW_IF = re.compile(r"([a-z]+(?: strike)?) if (you control an? [A-Z][a-z]+|it's (?:white|blue|black|red|green))")


def _keyword_ifs(m: re.Match[str]) -> Definition | None:
    from app.rules import statics

    pieces = [_KW_IF.fullmatch(x) for x in re.split(r", (?:and )?", m["list"])]
    each = m["s"].startswith("Each")
    if len(pieces) < 2 or not all(pieces) or any(p[2].startswith("it's") != each for p in pieces if p):
        return None  # (a condition on the creature goes with "each creature you control", one on what you control with the attached one)
    defs = [statics.parse(f"{m['s']} that's {p[2][5:]} has {p[1]}." if each else f"{m['s']} has {p[1]} as long as {p[2]}.") for p in pieces if p]
    if any(d is None for d in defs) or any(d["who"] != ("attached" if not each else d["who"]) or (not each and d.get("attached_kind") != "creature") for d in defs if d):
        return None
    first = dict(defs[0] or {})
    first["also"] = defs[1:]
    return first


def _not(conds: list[dict[str, Any]]) -> dict[str, Any]:
    return {"static": "not", "cond": conds[0] if len(conds) == 1 else {"static": "all", "conds": conds}}


def definition(text: str) -> Definition | None:
    from app.rules import joint_attached_pumps, statics

    if (joint := joint_attached_pumps.definition(text)) is not None:
        return joint

    # -- as long as (wave 25A) -- "As long as you control enchanted creature, it gets +2/+2.": "it" is the creature the condition names
    text = re.sub(r"^(As long as [^,]*\b(enchanted|equipped) creature\b[^,]*), it (?=(?:gets|has|can't)\b)",
                  lambda m: f"{m[1]}, {m[2].capitalize()} creature ", text.strip())
    from app.rules import abilities_of  # -- keyword inheritance (wave 25A) -- "The same is true for …"

    if (inherited := abilities_of.inherit(text, statics._definition)) is not None:
        return inherited
    # -- as long as (wave 25A) -- "As long as C, this creature and other Vampire creatures you control get +2/+1 and have flying.": two statics of the
    # same permanent under the same condition — itself, and the others (the single-sentence grammar reads a union subject only when it's plain)
    union = re.match(r"^(?P<head>As long as [^,]+), (?:~|this creature) and (?P<other>other [A-Z][a-z]+ creatures you control) (?P<pred>(?:get|have) .+)\.$",
                     text.strip())
    if union is not None:
        pred = re.sub(r"\bget\b", "gets", re.sub(r"\bhave\b", "has", union["pred"]))
        mine = statics.parse(f"{union['head']}, ~ {pred}.")
        others = statics.parse(f"{union['head']}, {union['other'].capitalize()} {union['pred']}.")
        if mine is None or others is None or mine.get("also") or others["who"] == "self":
            return None
        return {**mine, "also": [others]}
    # -- ability words (wave 46B) -- "Lieutenant — As long as you control your commander, this creature gets +2/+2 and other creatures you control get +2/+2 and have trample."
    # (Thunderfoot Baloth), "… gets +2/+2 and creatures you control have vigilance." (Angelic Field Marshal): the same two statics of one permanent under one condition
    both = re.match(r"^(?P<head>As long as [^,]+), (?:~|this creature) (?P<mine>(?:gets|has) .+?) and (?P<other>(?:other )?creatures you control (?:get|have) .+)\.$",
                    text.strip())
    if both is not None:
        mine, others = statics.parse(f"{both['head']}, ~ {both['mine']}."), statics.parse(f"{both['head']}, {both['other'].capitalize()}.")
        if mine is None or others is None or mine.get("also") or others["who"] == "self":
            return None
        return {**mine, "also": [others]}
    if (kw := _KW_IFS.match(text.strip())) is not None:  # -- most-played cards IV (wave 51G) -- one conditional grant for each "keyword if condition" part
        return _keyword_ifs(kw)
    # -- chosen filters (wave 53B) -- "Creatures you control of the chosen type get +1/+1. As long as you have the city's blessing, they also have vigilance." (Radiant
    # Destiny): "they" is the group of the first sentence, so the second is the same group's own conditional static (604.2, 611.3a)
    grp = re.fullmatch(r"(?P<s>[A-Z][^.,]*? you control of the chosen type) (?P<p>(?:get|have) [^.]+)\. As long as (?P<c>[^,.]+), they also (?P<q>have [^.]+)\.", text.strip())
    if grp is not None:
        first, second = statics.parse(f"{grp['s']} {grp['p']}."), statics.parse(f"As long as {grp['c']}, {grp['s']} {grp['q']}.")
        if first is None or second is None or first.get("also") or first["who"] in ("self", "attached") or first["who"] != second["who"]:
            return None
        return {**first, "also": [second]}
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
