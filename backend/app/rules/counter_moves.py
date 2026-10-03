"""-- moving counters (wave 12A) -- "Move all counters from ~ onto target creature." (The Ozolith), "Move a +1/+1 counter from
target creature onto a second target creature." (Daghatar), "Move a counter from target permanent you control onto a second
target permanent." (Nesting Grounds), "… you may move any number of +1/+1 counters from this creature onto another target
creature." (Scrounging Bandar), "move all +1/+1 counters from all creatures onto it" (Spike Cannibal). Researched against CR
2026-09-25.

* 122.5: moving removes the counter from the first object and puts it on a second. If either step is impossible (the same
  object twice, no counter of that kind on the first, the second can't have counters or is gone) nothing moves at all.
* The put is a put (122.6, 614.16): the counter choke point applies (Hardened Scales, Doubling Season).
* "a counter" without a kind: its controller chooses the kind when the first object has several; "any number": its
  controller chooses how many (608.2d, a decision for them).

Effect: ``{"do": "move_counters", "who": <to>, "from": <from> | absent (the source), "kind": k | None, "n": int | "all" | "any"}``.
Refused (manual): "any number of counters" of mixed kinds, moving onto several objects ("onto other creatures"), "a counter of each
kind not on ~", and anything riding on the number moved.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption
from app.rules import replace
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
STEP = "move_counters"


def move(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import effects

    if e.get("from"):
        sources = [c for c in effects._cards(plan, ctx, e["from"]) if plan.state.cards[c].zone.endswith(":battlefield")]
    else:
        sources = [c for c in effects._cards(plan, ctx, "self")]
    to = effects._cards(plan, ctx, e["who"])
    effects._remember(plan, ctx, e, to)
    if len(to) != 1 or not plan.state.cards[to[0]].zone.endswith(":battlefield"):
        return True  # 122.5: the second object is gone (or was never chosen): nothing moves
    sources = [c for c in sources if c != to[0]]  # (122.5: never the same object)
    have: dict[str, int] = {}
    for c in sources:
        for k, v in plan.state.cards[c].counters.items():
            if v > 0 and (not e.get("kind") or k == e["kind"]):
                have[k] = have.get(k, 0) + v
    if not have:
        return True
    n = e.get("n", "all")
    if n == "all":
        return _do(plan, ctx, e, sources, to[0], have)
    if len(have) > 1:  # "a counter": which kind (the controller's choice)
        decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'Move'}: choose a kind of counter",
               options=[DecisionOption(id=k, label=f"{k} counter") for k in sorted(have)], resume={"step": STEP, "ctx": ctx, "e": e})
        return False
    (kind, total), = have.items()
    if n == "any":  # how many (0 to all of them)
        decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'Move'}: how many {kind} counters?",
               options=[DecisionOption(id=str(i), label=str(i)) for i in range(total + 1)],
               resume={"step": STEP, "ctx": ctx, "e": e, "kind": kind})
        return False
    return _do(plan, ctx, e, sources, to[0], {kind: min(int(n), total)})


def _do(plan: Plan, ctx: Context, e: dict[str, Any], sources: list[str], to: str, amounts: dict[str, int]) -> bool:
    """Remove from the sources (the first object's counters first), then put them on the second (122.5)."""
    from app.rules import effects

    puts = []
    for kind, want in amounts.items():
        for c in sources:
            took = min(want, plan.state.cards[c].counters.get(kind, 0))
            if took > 0:
                plan.do({"type": "counter", "card_ids": [c], "kind": kind, "delta": -took}, actor=ctx["controller"])
                want -= took
                puts.append((to, kind, took))
    if not puts:
        return True
    return replace.put_counters(plan, puts, by=ctx["controller"], then=effects._then(ctx, e), ctx=ctx)


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    ctx, e = r["ctx"], r["e"]
    if len(chosen) != 1:
        raise ActionError("Choose one")
    if "kind" in r:  # a number of that kind
        if not chosen[0].isdigit():
            raise ActionError("Choose a number")
        concrete = {**e, "kind": r["kind"], "n": int(chosen[0])}
    else:  # a kind: it is "a counter" of it (or "any number" of it, chosen next)
        concrete = {**e, "kind": chosen[0]}
    plan.note(f"{plan.name(d.player)} chooses {chosen[0]}")
    at = ctx["next"] - 1
    ctx["effects"] = [*ctx["effects"][:at], concrete, *ctx["effects"][at + 1:]]
    ctx["next"] = at
    effects.continue_effects(plan, ctx)


PRIMITIVES = {"move_counters": move}
