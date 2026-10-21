"""Proposed mixed life instruction site; UNIMPORTED until parent diff review."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def plan_changes(plan: Plan, changes: list[list[Any]], *, answers: dict[str, str], ask: bool) -> Any:
    from app.rules import cant_gain, life_lock, replace

    # One candidate identity per physical replacement effect, including kind changes.
    pool = {c.id: c for c in replace.candidates(plan, ("life", "life_loss"))}
    planner = replace.Planner(plan, list(pool.values()), answers, ask=ask)
    sim: dict[str, Any] = {}
    order = plan.apnap()
    events = [
        {
            "kind": "life" if int(delta) > 0 else "life_loss",
            "player": pid,
            "n": abs(int(delta)),
            "key": str(i),
            "applied": [],
        }
        for i, (pid, delta) in enumerate(changes)
        if int(delta) and pid in plan.live()
    ]
    events.sort(key=lambda e: order.index(e["player"]) if e["player"] in order else len(order))
    finals = []
    try:
        for event in events:
            out: list[dict[str, Any]] = []

            def gate(ev: dict[str, Any], out: list[dict[str, Any]] = out) -> bool:
                if ev["kind"] not in ("life", "life_loss"):
                    return True
                if int(ev.get("n") or 0) <= 0:
                    return False
                why = (
                    cant_gain.why_not(plan, ev["player"])
                    if ev["kind"] == "life"
                    else life_lock.why_not(plan, ev["player"], "lose")
                )
                if why is not None:
                    out.append({"kind": "nothing", "why": [f"{why}: {ev['kind']} cannot happen"]})
                    return False
                return True

            planner.gate = gate
            planner.settle(event, sim, out.append)
            finals.append((event, out))
    except replace.Ask as question:
        return question
    return finals, planner


def _exchange_block(plan: Plan, request: dict[str, Any]) -> str | None:
    from app.rules import cant_gain, life_lock

    if request.get("mode") not in ("exchange", "stat"):
        return None
    if any(pid not in plan.live() for pid in request["participants"]):
        return "An exchange participant has left the game"
    stat = request.get("stat")
    if stat is not None:
        card = plan.state.cards.get(stat["card"])
        if (
            card is None
            or not card.zone.endswith(":battlefield")
            or plan.oid(card) != stat["oid"]
            or "Creature" not in plan.ch(card).types
            or plan.ch(card).pt is None
        ):
            return "The original creature is no longer available for the exchange"
    for pid, delta in request["changes"]:
        why = (
            cant_gain.why_not(plan, pid)
            if delta > 0
            else life_lock.why_not(plan, pid, "lose")
            if delta < 0
            else None
        )
        if why is not None:
            return f"{why}: the exchange cannot happen"
    return None


def _after(
    plan: Plan,
    request: dict[str, Any],
    ctx: dict[str, Any] | None,
    losses: dict[str, int],
    *,
    exchanged: bool,
) -> None:
    from app.rules import context, layers

    if request.get("bind") and ctx is not None:
        context.bind_amount(ctx, request["bind"], losses.get(request["actor"], 0))
    if exchanged and (stat := request.get("stat")) is not None:
        power = stat["kind"] == "power"
        layers.add_effect(
            plan,
            affected=[stat["oid"]],
            layer="7b",
            source=request.get("source_object"),
            controller=request["actor"],
            power=stat["life"] if power else None,
            toughness=None if power else stat["life"],
            duration="permanent",
            label=f"{stat['kind'].capitalize()} {stat['life']}",
        )


def change(
    plan: Plan,
    request: dict[str, Any],
    *,
    then: dict[str, Any] | None,
    answers: dict[str, str] | None = None,
    ctx: dict[str, Any] | None = None,
) -> bool:
    from app.rules import replace

    if (why := _exchange_block(plan, request)) is not None:
        plan.note(why, actor=request["actor"])
        _after(plan, request, ctx, {}, exchanged=False)
        return True
    answers = answers if answers is not None else replace._ctx_answers(ctx)
    planned = plan_changes(plan, request["changes"], answers=answers, ask=then is not None)
    if isinstance(planned, replace.Ask):
        continuation = (
            {"do": "continue", "ctx": then["ctx"]} if then and then.get("site") == "rerun" else then
        )
        frozen = {"site": "life_changes44", "request": request, "then": continuation}
        if replace._pause(plan, planned, answers, frozen):
            return False
        raise planned
    finals, planner = planned
    # Recheck before ANY mutation, including replacement consumption and atomic commit.
    if (why := _exchange_block(plan, request)) is not None:
        plan.note(why, actor=request["actor"])
        _after(plan, request, ctx, {}, exchanged=False)
        return True
    # Native life replacement operators emit only life, life_loss, or nothing.
    # Refuse an unhandled extension before consuming records or changing life.
    for _, out in finals:
        for event in out:
            if event["kind"] not in ("life", "life_loss", "nothing"):
                raise ValueError(f"Unsupported life replacement result: {event['kind']}")
    replace.left_to_players(plan, planner)
    for record in plan.rules.replacements:
        if (
            record.get("kind") == "replace"
            and (record.get("op") or {}).get("once")
            and f"r:{record['id']}" in planner.used
        ):
            record["spent"] = True
    changes = []
    losses: dict[str, int] = {}
    for before, out in finals:
        replace.note_applied(plan, before, out, actor=request["actor"])
        for event in out:
            if event["kind"] not in ("life", "life_loss") or int(event.get("n") or 0) <= 0:
                continue
            delta = int(event["n"]) * (-1 if event["kind"] == "life_loss" else 1)
            changes.append({"player": event["player"], "delta": delta})
            if delta < 0:
                losses[event["player"]] = losses.get(event["player"], 0) - delta
    if changes:
        # Preserve final events rather than netting, in ONE native table batch.
        plan.do(
            {"type": "rules_life_changes", "changes": changes, "group": request["operation"]},
            actor=request["actor"],
        )
    _after(plan, request, ctx, losses, exchanged=True)
    return True


def resume(plan: Plan, request: dict[str, Any], answers: dict[str, str], then: dict[str, Any] | None) -> None:
    from app.rules import replace

    ctx = (then or {}).get("ctx")
    if change(plan, request, then=then, answers=answers, ctx=ctx):
        replace.run_then(plan, then)


def set_life(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.rules import effects, replace

    desired = effect.get("values")
    changes = []
    for pid in effects._players(plan, ctx, effect["who"]):
        start = plan.state.settings.starting_life
        want = (
            int(desired[pid])
            if desired is not None
            else -(-start // 2)
            if effect["n"] == "half_start"
            else start // 2
            if effect["n"] == "half_start_down"
            else effects._amount(plan, {**ctx, "recipient": pid}, effect["n"])
        )
        changes.append([pid, want - plan.state.players[pid].life])
    request = {
        "mode": "set",
        "changes": changes,
        "actor": ctx["controller"],
        "operation": replace._life_operation(plan, None),
    }
    return change(plan, request, then=effects._then(ctx, effect), ctx=ctx)


def exchange_life(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.rules import effects, replace

    if effect.get("bind"):
        from app.rules import context

        context.bind_amount(ctx, effect["bind"], 0)
    players = list(
        dict.fromkeys(
            [ctx["controller"], *effects._players(plan, ctx, effect["with"])]
            if effect.get("with")
            else effects._players(plan, ctx, effect["who"])
        )
    )
    if len(players) != 2:
        return True
    a, b = players
    difference = plan.state.players[b].life - plan.state.players[a].life
    request = {
        "mode": "exchange",
        "participants": players,
        "changes": [[a, difference], [b, -difference]],
        "actor": ctx["controller"],
        "bind": effect.get("bind"),
        "operation": replace._life_operation(plan, None),
    }
    return change(plan, request, then=effects._then(ctx, effect), ctx=ctx)


def exchange_life_stat(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.rules import effects, replace

    players = effects._players(plan, ctx, effect["who"])
    card = plan.state.cards.get(ctx.get("source_card") or "")
    if (
        len(players) != 1
        or card is None
        or not card.zone.endswith(":battlefield")
        or plan.oid(card) != ctx.get("source_object")
    ):
        return True
    pt = plan.ch(card).pt
    if pt is None or "Creature" not in plan.ch(card).types:
        return True
    life = plan.state.players[players[0]].life
    value = pt[0 if effect["stat"] == "power" else 1]
    request = {
        "mode": "stat",
        "participants": players,
        "changes": [[players[0], value - life]],
        "actor": ctx["controller"],
        "source_object": ctx.get("source_object"),
        "stat": {"card": card.id, "oid": plan.oid(card), "kind": effect["stat"], "life": life},
        "operation": replace._life_operation(plan, None),
    }
    return change(plan, request, then=effects._then(ctx, effect), ctx=ctx)
