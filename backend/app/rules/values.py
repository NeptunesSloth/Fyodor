"""Quantities in effects ("draw two cards", "X damage", "a +1/+1 counter for each creature you
control"): explicit, deterministic expressions evaluated at resolution (608.2h: values are
determined as the effect is carried out).

A value is an int (a literal) or a dict:

* ``{"x": 1}`` — the X the spell or ability was cast / activated with (107.3);
* ``{"count": "<selector key>"}`` — the number of objects (or players) matching a selector;
* ``{"hand": "you"}`` — the number of cards in a player's hand;
* ``{"opponents": 1}`` — the number of opponents still in the game;
* ``{"power": "self" | "target"}`` / ``{"toughness": …}`` / ``{"mana_value": …}`` — of an object;
* ``{"counters": kind, "on": "self"}`` — counters of a kind on an object;
* ``{"times": [a, b]}`` — a product (e.g. "two for each …").

Parsing lives in :func:`parse_amount` (words) and :func:`parse_count` ("the number of …").
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.rules import selectors

if TYPE_CHECKING:
    from app.rules.plan import Plan

Value = int | dict[str, Any]
NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
           "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "twenty": 20}
AMOUNT = r"(?:\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|x)"


def parse_amount(word: str) -> Value | None:
    w = word.strip().lower()
    if w.isdigit():
        return int(w)
    if w in NUMBERS:
        return NUMBERS[w]
    if w == "x":
        return {"x": 1}
    return None


_COUNT = re.compile(r"^the number of (?P<what>.+?)$")


def parse_count(phrase: str) -> Value | None:
    """"the number of creatures you control" / "cards in your hand" / "opponents you have"."""
    m = _COUNT.match(phrase.strip())
    what = m["what"] if m else phrase.strip()
    if what in ("cards in your hand",):
        return {"hand": "you"}
    if what in ("opponents you have", "your opponents"):
        return {"opponents": 1}
    sel = selectors.parse(what)
    if sel is None:
        return None
    return {"count": sel.key()}


def evaluate(plan: Plan, ctx: dict[str, Any], v: Value) -> int:
    """The number a value stands for right now (never negative)."""
    if isinstance(v, int):
        return max(0, v)
    you = ctx["controller"]
    if "x" in v:
        return max(0, int(ctx.get("x") or 0))
    if "times" in v:
        a, b = v["times"]
        return evaluate(plan, ctx, a) * evaluate(plan, ctx, b)
    if "count" in v:
        sel = selectors.from_key(v["count"])
        if sel.player is not None:
            return sum(1 for p in plan.live() if selectors.matches_player(plan, sel, p, you))
        return len(selectors.candidates(plan, sel, you, ctx.get("source_card")))
    if "hand" in v:
        return len(plan.state.zones.get(f"{you}:hand", []))
    if "opponents" in v:
        return sum(1 for p in plan.live() if p != you)
    for stat in ("power", "toughness", "mana_value"):
        if stat in v:
            card = _object(plan, ctx, v[stat])
            if card is None:
                return 0
            ch = plan.ch(card)
            if stat == "mana_value":
                return int(ch.mana_value)
            value = ch.pt[0 if stat == "power" else 1] if ch.pt is not None else None
            raw = ch.power if stat == "power" else ch.toughness
            if value is None and raw is not None and raw.lstrip("-").isdigit():
                value = int(raw)
            return max(0, value or 0)
    if "counters" in v:
        card = _object(plan, ctx, v.get("on", "self"))
        return card.counters.get(v["counters"], 0) if card is not None else 0
    raise ValueError(f"unknown value {v!r}")


def _object(plan: Plan, ctx: dict[str, Any], who: str) -> Any:
    if who == "self":
        return plan.state.cards.get(ctx.get("source_card") or "")
    if who == "target":
        for t in ctx.get("targets") or []:
            card = plan.state.cards.get(t["id"])
            if card is not None:
                return card
    return None
