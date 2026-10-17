"""-- keyword soups (wave 50J) -- "creatures you control gain first strike until end of turn if a creature you control has first strike. The same is
true for flying, deathtouch, …" (Odric, Lunarch Marshal; Majestic Myriarch, Bleeding Effect, Concerted Effort), "each other creature you control gets
+1/+1 if it has flying, +1/+1 if it has first strike, and so on for …" (Akroma, Vision of Ixidor), "the number of abilities from among flying, … found
among creatures you control" (Odric, Blood-Cursed).

Each listed keyword is its own check, all made as the ability resolves (611.2c: the creatures affected and what they gain are fixed then; Odric's rulings).
A creature "has" a keyword by any variant of it (702.11d: "hexproof from white" is a variant of hexproof) and the objects gain the variant as the holder
has it (the ruling of 2020-01-24); several creatures with the same ability are the one ability. "Partner" is partner and partner with, not "Partner—Character
select" (Akroma's ruling). The lines come from ``oracle.keyword_pieces``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.rules import oracle, selectors

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

Context = dict[str, Any]
WORDS = frozenset({"flying", "first strike", "double strike", "deathtouch", "haste", "hexproof", "indestructible", "lifelink", "menace", "reach", "skulk",
                   "trample", "vigilance", "fear", "landwalk", "protection", "partner"})
_LIST = r"(?P<ks>[a-z ]+(?:, [a-z ]+)*(?:,? and [a-z ]+)?)"
_SRC = {"a creature you control has": "creature you control", "a creature card in your graveyard has": "creature card in your graveyard",
        "you control a creature with": "creature you control"}
_GRANT = re.compile(rf"^(?P<who>[Cc]reatures you control|~|[Tt]his creature|[Ii]t) gains? (?P<k>[a-z ]+?) until end of turn if (?P<src>{'|'.join(_SRC)}) (?P=k)\. "
                    rf"The same is true for {_LIST}\.$")
_PUMP = re.compile(rf"^(?:[Uu]ntil end of turn, )?each other creature you control gets \+1/\+1 if it has (?P<k>[a-z ]+?), \+1/\+1 if it has (?P<k2>[a-z ]+?), "
                   rf"and so on for {_LIST}\.$")


def words(text: str) -> list[str] | None:
    """"a, b, and c" → the keywords, when every one is read."""
    found = [w.strip() for w in re.split(r", and |, | and ", text) if w.strip()]
    return found if found and len(set(found)) == len(found) and set(found) <= WORDS else None


def bind(body: str, it: str | None) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """The effects of a keyword soup sentence pair (scripts._parse_effects_plain), or None."""
    if (m := _GRANT.match(body.strip())) is not None:
        ks = words(", ".join([m["k"], m["ks"]]))
        who = m["who"].lower()
        you = selectors.parse("creature you control")
        src = selectors.parse(_SRC[m["src"]])
        if ks is None or you is None or src is None or (who == "it" and it != "self"):
            return None
        return [{"do": "keyword_soup", "mode": "grant", "keywords": ks, "from": src.key(),
                 "who": you.key() if who == "creatures you control" else "self"}], None, False
    if (m := _PUMP.match(body.strip())) is not None:
        ks = words(", ".join([m["k"], m["k2"], m["ks"]]))
        other = selectors.parse("other creature you control")
        return None if ks is None or other is None else ([{"do": "keyword_soup", "mode": "pump", "keywords": ks, "who": other.key()}], None, False)
    return None


def _matches(word: str, name: str, text: str) -> bool:
    if word == "partner":  # (Akroma's ruling: not "Partner—Character select", "Partner—Friends forever")
        return bool(re.fullmatch(r"partner(?: with .+)?", text.lower()))
    return name == word or (word == "hexproof" and name == "hexproof from") or (word == "landwalk" and name.endswith("walk"))


def lines(plan: Plan, card: CardInstance, ks: list[str]) -> dict[str, dict[str, bool]]:
    """The abilities ``card`` has among ``ks``: word → {the ability as written → whether it is the plain keyword (granted as a keyword, not a line)}."""
    ch = plan.ch(card)
    found: dict[str, dict[str, bool]] = {}
    for ab in ch.abilities:
        if ab.kind != "keywords":
            continue
        for name, piece in zip(ab.keywords, oracle.keyword_pieces(ab.text) if len(ab.keywords) > 1 else [ab.text], strict=True):
            for w in ks:
                if name in ch.keywords and _matches(w, name, piece.strip()):
                    found.setdefault(w, {})[piece.strip(" .")] = piece.strip(" .").lower() == name
    for name in ch.granted & ch.keywords:  # (a keyword granted by a static or an effect: no line)
        for w in ks:
            if _matches(w, name, name):
                found.setdefault(w, {})[name] = True
    return found


def soup(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import effects, layers

    holders = [plan.state.cards[c] for c in effects._cards(plan, ctx, e.get("from") or e["who"])]
    if e["mode"] == "grant":
        got: dict[str, tuple[str, bool]] = {}  # (several creatures with an ability are the one ability)
        for holder in holders:
            for found in lines(plan, holder, e["keywords"]).values():
                for text, plain in found.items():
                    got[text.lower()] = (text, plain or got.get(text.lower(), ("", False))[1])
        if got:  # (a plain keyword is granted as one, the rest as the lines they are)
            effects.grant(plan, ctx, {"do": "grant", "who": e["who"], "keywords": [k for k, (_, plain) in got.items() if plain],
                                      "abilities": [t for t, plain in got.values() if not plain]})
        return True
    groups: dict[int, list[str]] = {}  # the bonus is the number of listed abilities each has, counted now (611.2c)
    for card in holders:
        if n := len(lines(plan, card, e["keywords"])):
            groups.setdefault(n, []).append(card.id)
    for n, ids in sorted(groups.items()):
        layers.add_effect(plan, affected=[plan.oid(c) for c in ids], layer="7c", source=ctx.get("source_object"), controller=ctx["controller"], power=n,
                          toughness=n, duration="end_of_turn", label=f"+{n}/+{n} until end of turn ({ctx.get('name', '')})")
        effects._mark(plan, ids, f"+{n}/+{n}")
    return True


def count(plan: Plan, ctx: Context, key: str, ks: list[str]) -> int:
    """"the number of abilities from among … found among <creatures>": the listed abilities any of them has (Odric, Blood-Cursed's ruling)."""
    found: set[str] = set()
    for c in selectors.candidates(plan, selectors.from_key(key), ctx["controller"], ctx.get("source_card")):
        found |= set(lines(plan, plan.state.cards[c], ks))
    return len(found)
