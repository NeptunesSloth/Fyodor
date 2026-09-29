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
* ``{"times": [a, b]}`` — a product (e.g. "two for each …");
* ``{"event_amount": 1}`` — "that much" / "that many": the trigger event's amount, read from the
  context the ability carries from when it triggered (app.game.rules_state.TriggerEvent).
* ``{"kicked": 1}`` — the number of times the spell (or the permanent it became) was kicked
  (702.33d; "for each time it was kicked").

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
AMOUNT = r"(?:\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|x|X|that much|that many)"

# Counters that carry rules the engine doesn't model yet (122.1b keyword counters, 122.1c shield,
# 122.1d stun, 122.1h finality, 122.1i rad, 122.1j hone, 714 lore): an effect putting one of these
# stays manual rather than placing an inert marker.
UNMODELED_COUNTERS = frozenset({
    "flying", "first strike", "double strike", "deathtouch", "decayed", "exalted", "haste", "hexproof",
    "indestructible", "lifelink", "menace", "reach", "shadow", "trample", "vigilance",
    "shield", "stun", "finality", "rad", "hone", "lore"})


def parse_amount(word: str) -> Value | None:
    w = word.strip().lower()
    if w.isdigit():
        return int(w)
    if w in NUMBERS:
        return NUMBERS[w]
    if w == "x":
        return {"x": 1}
    if w in ("that much", "that many"):
        return {"event_amount": 1}  # the trigger event's amount (TriggerEvent.amount)
    return None


_COUNT = re.compile(r"^the number of (?P<what>.+?)$")


def parse_count(phrase: str) -> Value | None:
    """"the number of creatures you control" / "cards in your hand" / "opponents you have"."""
    m = _COUNT.match(phrase.strip())
    what = m["what"] if m else phrase.strip()
    if what in ("cards in your hand",):
        return {"hand": "you"}
    if what in ("opponents you have", "opponent you have", "your opponents", "opponent"):
        return {"opponents": 1}
    if what in ("time it was kicked", "time this spell was kicked", "time ~ was kicked"):
        return {"kicked": 1}
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
    if "kicked" in v:
        return kicked_count(plan, ctx)
    if "count" in v:
        sel = selectors.from_key(v["count"])
        if sel.player is not None:
            return sum(1 for p in plan.live() if selectors.matches_player(plan, sel, p, you))
        return len(selectors.candidates(plan, sel, you, ctx.get("source_card")))
    if "event_amount" in v:  # "that much" / "that many": the trigger event's amount (608.2k)
        from app.rules import context  # (context → triggers → … → values)

        return context.amount(ctx, context.EVENT)
    if "ref_amount" in v:  # "that much" of an earlier effect of this resolution (app/rules/context.py)
        from app.rules import context

        return context.amount(ctx, v["ref_amount"])
    if "event_count" in v:  # how many objects the "one or more" batch had
        return max(0, int((ctx.get("event") or {}).get("count") or 0))
    if "hand" in v:
        return len(plan.state.zones.get(f"{you}:hand", []))
    if "opponents" in v:
        return sum(1 for p in plan.live() if p != you)
    for stat in ("power", "toughness", "mana_value"):
        if stat in v:
            got = _object(plan, ctx, v[stat])
            if got is None:
                return 0
            _, ch = got
            if stat == "mana_value":
                return int(ch.mana_value)
            value = ch.pt[0 if stat == "power" else 1] if ch.pt is not None else None
            raw = ch.power if stat == "power" else ch.toughness
            if value is None and raw is not None and raw.lstrip("-").isdigit():
                value = int(raw)
            return max(0, value or 0)
    if "counters" in v:
        got = _object(plan, ctx, v.get("on", "self"))
        return got[0].counters.get(v["counters"], 0) if got is not None else 0
    raise ValueError(f"unknown value {v!r}")


def kicked_count(plan: Plan, ctx: dict[str, Any]) -> int:
    """702.33d: how many times the spell resolving (or copied, 707.10) was kicked; for an ability
    of a permanent, how many times the spell it was cast as was (its payment record)."""
    entry = plan.rules.stack.get(ctx.get("stack_id") or "")
    if entry is not None and entry.kind == "spell":
        return entry.kicked
    record = plan.rules.payments.get(ctx.get("source_object") or "")
    return record.kicked if record is not None else 0


def _object(plan: Plan, ctx: dict[str, Any], who: str) -> tuple[Any, Any] | None:
    """The object a value reads ("its power", "the target's toughness") and its characteristics:
    as it is now while it's still that object, else as it last existed (608.2h, 400.7). An
    object id with no current object and no last known information reads as nothing."""
    refs: list[tuple[str, str | None]] = []
    if who == "self":
        refs = [(ctx.get("source_card") or "", ctx.get("source_object"))]
    elif who == "target" or who.startswith("target:"):
        from app.rules.effects import target_refs  # (effects imports this module)

        refs = [(t["id"], t.get("object_id")) for t in target_refs(ctx, who)]
    if who == "event" or who.startswith("ref:"):  # the trigger event's object, or an earlier effect's
        from app.rules import context  # (as it is, or as it last existed: 603.10a, 608.2h)

        return context.info(plan, ctx, context.EVENT if who == "event" else who[4:])
    for card_id, oid in refs:
        card = plan.state.cards.get(card_id)
        if card is not None and (oid is None or plan.oid(card) == oid):
            return card, plan.ch(card)
        snap = plan.rules.lki.get(oid or "")
        if snap is not None:
            from app.rules.triggers import _snapshot_card  # (triggers imports this module's users)

            return _snapshot_card(plan, snap)
    return None
