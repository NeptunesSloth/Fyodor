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
"Move any number of counters from target permanent you control onto a second target permanent" (wave 24C: Resourceful Defense) asks
how many of each kind, kind by kind (counter_kinds.ask_amounts). Refused (manual): "any number of counters" from a group of sources
(which object each comes off is the player's choice), moving onto several objects ("onto other creatures"), "a counter of each
kind not on ~", and anything riding on the number moved.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption, ObjectRef
from app.rules import replace
from app.rules.counter_receipts import CounterPlacement
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
STEP = "move_counters"


def move(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import context, effects, prohibitions

    if e.get("from"):
        sources = [c for c in effects._cards(plan, ctx, e["from"]) if plan.state.cards[c].zone.endswith(":battlefield")]
    else:
        sources = [c for c in effects._cards(plan, ctx, "self")]
    to = effects._cards(plan, ctx, e["who"])
    effects._remember(plan, ctx, e, to)
    if len(to) != 1 or not plan.state.cards[to[0]].zone.endswith(":battlefield"):
        _record_receipt(ctx, e, CounterMoveReceipt())
        return True  # 122.5: the second object is gone (or was never chosen): nothing moves
    sources = [c for c in sources if c != to[0]]  # (122.5: never the same object)
    have: dict[str, int] = {}
    for c in sources:
        for k, v in plan.state.cards[c].counters.items():
            if v > 0 and (not e.get("kind") or k == e["kind"]) and not prohibitions.cant_remove_counters(plan, c, k):
                have[k] = have.get(k, 0) + v
    if not have:
        _record_receipt(ctx, e, CounterMoveReceipt())
        return True
    n = e.get("n", "all")
    if n == "all":
        return _do(plan, ctx, e, sources, to[0], have)
    if n == "any" and not e.get("kind"):  # -- counter kinds (wave 24C) -- "any number of counters": how many of each kind, in turn
        from app.rules import counter_kinds

        target_ref = context.ref_of(plan, to[0])
        if target_ref is None:
            _record_receipt(ctx, e, CounterMoveReceipt())
            return True
        return counter_kinds.ask_amounts(plan, ctx, e, have, {"do": "move", "from": sources, "to": to[0],
            "source_refs": [ref.model_dump(mode='json') for cid in sources if (ref := context.ref_of(plan, cid)) is not None],
            "destination_ref": target_ref.model_dump(mode='json')})
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


def finish(plan: Plan, ctx: Context, e: dict[str, Any], sources: list[str], to: str, amounts: dict[str, int], *,
           source_refs: list[ObjectRef] | None = None, destination_ref: ObjectRef | None = None) -> bool:
    return _do(plan, ctx, e, sources, to, amounts, source_refs=source_refs, destination_ref=destination_ref)


class CounterTransfer(BaseModel):
    source: ObjectRef
    destination: ObjectRef
    kind: str
    amount: int


class CounterMoveReceipt(BaseModel):
    """Performed removals and placements, deliberately separate quantities.

    A put replacement can add, multiply, or contract the destination quantity.
    No consumer may silently equate either field to "counters moved this way".
    """
    removed: list[CounterTransfer] = Field(default_factory=list)
    placed: list[CounterPlacement] = Field(default_factory=list)


class CounterMoveFrame(BaseModel):
    ctx: dict[str, Any]
    effect: dict[str, Any]
    transfers: list[CounterTransfer] = Field(default_factory=list)


def _record_receipt(ctx: Context, effect: dict[str, Any], receipt: CounterMoveReceipt) -> None:
    if effect.get('receipt'):
        ctx.setdefault('counter_move_receipts', {})[effect['receipt']] = receipt.model_dump(mode='json')


def _do(plan: Plan, ctx: Context, e: dict[str, Any], sources: list[str], to: str, amounts: dict[str, int], *,
        source_refs: list[ObjectRef] | None = None, destination_ref: ObjectRef | None = None) -> bool:
    """122.5: plan a permitted remove+put before performing either action."""
    from app.rules import context

    target = destination_ref or context.ref_of(plan, to)
    refs = source_refs if source_refs is not None else [ref for cid in dict.fromkeys(sources)
                                                      if (ref := context.ref_of(plan, cid)) is not None]
    transfers = []
    if target is not None:
        for kind, want in amounts.items():
            for ref in refs:
                source = context._same(plan, ref)
                if source is None or not source.zone.endswith(':battlefield') or ref.object_id == target.object_id:
                    continue
                took = min(max(0, want), max(0, source.counters.get(kind, 0)))
                if took:
                    transfers.append(CounterTransfer(source=ref, destination=target, kind=kind, amount=took))
                    want -= took
    frame = CounterMoveFrame(ctx=ctx, effect=e, transfers=transfers)
    frame.ctx = ctx  # Preserve the resolver's live context on synchronous completion.
    return _perform(plan, frame, replace._ctx_answers(ctx))


def _perform(plan: Plan, frame: CounterMoveFrame, answers: dict[str, str]) -> bool:
    from app.rules import context, counter_removal_results, prohibitions

    live: list[CounterTransfer] = []
    puts: dict[tuple[str, str], int] = {}
    for transfer in frame.transfers:
        source = context._same(plan, transfer.source)
        target = context._same(plan, transfer.destination)
        if (source is None or target is None or not source.zone.endswith(':battlefield')
                or not target.zone.endswith(':battlefield') or source.id == target.id):
            continue
        if (prohibitions.cant_remove_counters(plan, source.id, transfer.kind)
                or prohibitions.cant_counters(plan, target.id, None, transfer.kind)):
            continue  # Neither action is possible: keep the original counters.
        amount = min(transfer.amount, max(0, source.counters.get(transfer.kind, 0)))
        if amount <= 0:
            continue
        actual = transfer.model_copy(update={'amount': amount})
        live.append(actual)
        key = (target.id, transfer.kind)
        puts[key] = puts.get(key, 0) + amount
    receipt = CounterMoveReceipt()
    if not live:
        _record_receipt(frame.ctx, frame.effect, receipt)
        return True
    planned = replace.plan_counters(plan, [(cid, kind, n) for (cid, kind), n in puts.items()],
                                    by=frame.ctx['controller'], effect=True, entering=None, answers=answers, ask=True)
    if isinstance(planned, replace.Ask):
        replace.ask(plan, planned, answers, {'site': 'counter_move_commit',
                                            'request': {'frame': frame.model_dump(mode='json')}})
        return False
    # No legal game action happens during replacement choices. The exact refs
    # above also make cold restored/table-edited choices safe to finish.
    for transfer in live:
        removed = counter_removal_results.remove(plan, transfer.source.card, transfer.kind,
                                                 transfer.amount, by=frame.ctx['controller'])
        if removed != transfer.amount:
            raise ActionError('The selected counters can no longer be moved')
        receipt.removed.append(transfer)
    replace.do_counters(plan, planned, by=frame.ctx['controller'], receipt=receipt.placed)
    _record_receipt(frame.ctx, frame.effect, receipt)
    return True


def _resume_move(plan: Plan, request: dict[str, Any], answers: dict[str, str], then: dict[str, Any] | None) -> None:
    from app.rules import effects

    frame = CounterMoveFrame.model_validate(request['frame'])
    if _perform(plan, frame, answers):
        effects.continue_effects(plan, frame.ctx)


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
replace.SITES["counter_move_commit"] = _resume_move
