"""-- Doctor Who keywords (wave 25A) -- time travel (CR 701.56), researched against the stored Comprehensive Rules (2026-09-25).

* 701.56a — "To time travel means to choose any number of permanents you control with one or more time counters on them and/or suspended
  cards you own in exile with one or more time counters on them and, for each of those objects, put a time counter on it or remove a time
  counter from it." The choices are the controller's (a pick of the objects, then add or remove for each, one at a time); the counters
  change together, through the counter choke point (``replace.put_counters``: a counter-doubling replacement applies to the ones put on,
  614.1a, 616.1; removing isn't replaceable).
* 702.62c — "When the last time counter is removed from this card, if it's exiled, its owner may play it without paying its mana cost":
  a suspended card whose last time counter time travel took off has that triggered ability, put on the stack after the time travel
  resolves (``cast_offer``: it checks, as it resolves, that the card is still exiled with no time counter on it).
* 702.63a vanishing's own "when the last time counter is removed" trigger is the permanent's (keyword_triggers) and fires from the counter event.
* "Time travel three times" / "Time travel, then time travel": each one is a whole time travel (701.56a), one after the other.

Nothing here is hidden: the objects are permanents and exiled cards, public. A time travel with nothing to choose does nothing.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.effects import Context
    from app.rules.plan import Plan

_WORDS = {"once": 1, "twice": 2, "two times": 2, "three times": 3, "four times": 4, "five times": 5}
PATTERN = r"time travel(?P<times> once| twice| (?:two|three|four|five) times|(?:, then time travel)+)?"


def build(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    times = (m["times"] or "").strip()
    n = 1 + times.count("then") if times.startswith(",") else _WORDS.get(times, 1)
    return [{"do": "time_travel"} for _ in range(n)], None


def candidates(plan: Plan, me: str) -> list[str]:
    """701.56a: the permanents ``me`` controls and the suspended cards ``me`` owns in exile, each with a time counter."""
    r = plan.rules
    out = []
    for cid, c in plan.state.cards.items():
        if c.counters.get("time", 0) <= 0 or plan.manual(c):
            continue
        if (c.zone == f"{me}:battlefield" and c.controller == me) or (c.zone.endswith(":exile") and c.owner == me and cid in r.suspended):
            out.append(cid)
    return out


def time_travel(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules.effects import decide

    me = ctx["controller"]
    found = candidates(plan, me)
    if not found:
        plan.note(f"{plan.name(me)} time travels: no permanent or suspended card to choose")
        return True
    decide(plan, player=me, kind="choose_cards", prompt=f"{ctx.get('name') or 'Time travel'}: choose any number of permanents and suspended cards "
           "with time counters", options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in found],
           min_choices=0, max_choices=len(found), resume={"step": "time_travel", "ctx": ctx})
    return False


def resume_pick(plan: Plan, d: Any, chosen: list[str]) -> None:
    ok = [c for c in chosen if c in candidates(plan, d.player)]
    _next(plan, d.resume["ctx"], d.player, ok, [])


def _next(plan: Plan, ctx: Context, me: str, left: list[str], done: list[list[Any]]) -> None:
    """One chosen object at a time: put a time counter on it or remove one (701.56a)."""
    from app.rules.effects import decide

    if left:
        cid = left[0]
        name = plan.state.cards[cid].name or "Card"
        decide(plan, player=me, kind="choose_one", prompt=f"{ctx.get('name') or 'Time travel'}: {name} ({plan.state.cards[cid].counters.get('time', 0)} time counters)",
               options=[DecisionOption(id="add", label="Put a time counter on it", card_id=cid),
                        DecisionOption(id="remove", label="Remove a time counter from it", card_id=cid)],
               resume={"step": "time_travel_each", "ctx": ctx, "left": left, "done": done})
        return
    _apply(plan, ctx, me, done)


def resume_each(plan: Plan, d: Any, chosen: list[str]) -> None:
    left, done = list(d.resume["left"]), [list(x) for x in d.resume["done"]]
    cid = left.pop(0)
    if cid in plan.state.cards and chosen[0] in ("add", "remove"):
        done.append([cid, "time", 1 if chosen[0] == "add" else -1])
    _next(plan, d.resume["ctx"], d.player, left, done)


def _apply(plan: Plan, ctx: Context, me: str, done: list[list[Any]]) -> None:
    """The counters change together; a suspended card that lost its last one has 702.62c's trigger (put on the stack once this resolves)."""
    from app.rules import replace
    from app.rules.effects import continue_effects

    if done and not replace.put_counters(plan, [(c, k, n) for c, k, n in done], by=me, then={"do": "continue", "ctx": ctx}, ctx=ctx):
        return  # (a replacement order is being asked: the resolution goes on after the answer)
    continue_effects(plan, ctx)


def cast_offer(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """702.62c: the suspended card whose last time counter was removed — still exiled, no time counter left — may be cast for free."""
    from app.rules import effects

    card = plan.state.cards.get(e["card"])
    if card is None or not card.zone.endswith(":exile") or card.counters.get("time", 0) > 0 or e["card"] not in plan.rules.suspended:
        return True
    return effects.free_cast_offer(plan, ctx, e)


PRIMITIVES = {"time_travel": time_travel, "time_travel_cast": cast_offer}
RESUME = {"time_travel": resume_pick, "time_travel_each": resume_each}
