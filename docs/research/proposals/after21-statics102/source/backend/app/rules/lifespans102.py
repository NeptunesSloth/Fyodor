"""Original-object relation durations, CR 611.2b and 702.26f (2026-09-25)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import DurationBound102

if TYPE_CHECKING:
    from app.rules.plan import Plan


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    body = body.strip()
    suffix = " for as long as that creature is enchanted"
    if body.rstrip(".").endswith(suffix):
        base = body.rstrip(".")[: -len(suffix)]
        if base == "Gain control of target creature":
            got = scripts.parse_effects(base + ".")
            if got is not None:
                es, target, multiple = got
                return (
                    [{"do": "bound102", "kind": "enchanted", "who": "target", "n": len(es)}, *es],
                    target,
                    multiple,
                )
    if body.rstrip(".") == (
        "Tap another target nonland permanent. Its activated abilities can't be activated "
        "for as long as it remains tapped"
    ):
        got = scripts.parse_effects("Tap another target nonland permanent.")
        if got is not None:
            es, target, multiple = got
            return (
                [
                    *es,
                    {"do": "bound102", "kind": "tapped", "who": "target", "n": 1},
                    {"do": "restrict", "who": "target", "rules": ["cant_activate"], "duration": "permanent"},
                ],
                target,
                multiple,
            )
    if body.rstrip(".") == (
        "Tap another target creature and put a stun counter on it. "
        "~ becomes a copy of that creature for as long as that creature remains tapped"
    ):
        got = scripts.parse_effects("Tap another target creature and put a stun counter on it.")
        if got is not None:
            es, target, multiple = got
            return (
                [
                    *es,
                    {"do": "bound102", "kind": "tapped", "who": "target", "n": 1},
                    {"do": "become_copy", "who": "self", "with": "target", "duration": "permanent"},
                ],
                target,
                multiple,
            )
    if body.rstrip(".") == (
        "Gain control of target creature with power less than or equal to ~'s power "
        "for as long as ~ remains tapped and that creature's power remains less than or equal to ~'s power"
    ):
        got = scripts.parse_effects(
            "Gain control of target creature with power less than or equal to ~'s power."
        )
        if got is not None:
            es, target, multiple = got
            return (
                [{"do": "bound102", "kind": "source_tapped_power", "who": "target", "n": len(es)}, *es],
                target,
                multiple,
            )
    return None


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    text = scripts.self_text(ability.text, ch.name)
    if text == (
        "Whenever ~ becomes attached to a creature, for as long as ~ remains attached to it, "
        "you may have that creature become a copy of another target creature you control."
    ):
        return {
            "kind": "triggered",
            "trigger": "event",
            "optional": True,
            "attached_other102": True,
            "cond": {
                "subject": "self",
                "event": "attached",
                "other": selectors.Selector(types=("Creature",)).key(),
            },
            "target": {
                "what": selectors.Selector(types=("Creature",), controller="you", extras=("not_event",)).key()
            },
            "effects": [
                {"do": "bound102", "kind": "attached", "who": "event", "n": 1},
                {"do": "become_copy", "who": "event", "with": "target", "duration": "permanent"},
            ],
        }
    if text == (
        "Whenever ~ becomes attached to a creature, for as long as ~ remains attached to it, "
        "that creature becomes a copy of a creature card exiled with ~."
    ):
        from app.rules import exiled_with

        return exiled_with.link(
            {
                "kind": "triggered",
                "trigger": "event",
                "optional": False,
                "cond": {
                    "subject": "self",
                    "event": "attached",
                    "other": selectors.Selector(types=("Creature",)).key(),
                },
                "target": None,
                "effects": [
                    {"do": "pick_linked_copy102", "who": "exiled_with"},
                    {"do": "bound102", "kind": "attached", "who": "event", "n": 1},
                    {
                        "do": "become_copy",
                        "who": "event",
                        "with": "ref:linked_copy102",
                        "duration": "permanent",
                    },
                ],
            },
            ability,
            ch,
        )
    return None


def capture(definition: dict[str, Any], event: Any) -> dict[str, Any]:
    """Freeze another relative to the original recipient, not its reusable physical ID."""
    from app.rules import selectors

    if (
        not definition.get("attached_other102")
        or event is None
        or event.kind != "attached"
        or len(event.objects) != 1
    ):
        return definition
    target = definition["target"]
    sel = selectors.from_key(target["what"])
    extras = tuple(
        "not_oid:" + event.objects[0].object_id if value == "not_event" else value for value in sel.extras
    )
    return {**definition, "target": {**target, "what": selectors.replace(sel, extras=extras).key()}}


def holds(plan: Plan, bound: DurationBound102) -> bool:
    target = next((c for c in plan.state.cards.values() if plan.oid(c) == bound.target_object), None)
    if target is None or not target.zone.endswith(":battlefield") or not plan.in_game(target):
        return False
    if bound.kind == "tapped":
        return target.tapped
    if bound.kind == "enchanted":
        return any(
            c.attached_to == target.id
            and c.zone.endswith(":battlefield")
            and plan.in_game(c)
            and "Aura" in plan.ch(c).subtypes
            for c in plan.state.cards.values()
        )
    source = plan.state.cards.get(bound.source_card or "")
    if (
        source is None
        or not source.zone.endswith(":battlefield")
        or not plan.in_game(source)
        or plan.oid(source) != bound.source_object
    ):
        return False
    if bound.kind == "attached":
        return source.attached_to == target.id
    a, b = plan.ch(target).pt, plan.ch(source).pt
    return source.tapped and (a[0] if a is not None else 0) <= (b[0] if b is not None else 0)  # 107.2, 208.3


def apply(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import delayed, effects

    start, n = ctx["next"], int(e["n"])
    inner = ctx["effects"][start : start + n]
    ctx["next"] = start + n
    cards = effects._cards(plan, ctx, e["who"])
    if len(cards) != 1:
        return True
    bound = DurationBound102(
        kind=e["kind"],
        target_object=plan.oid(cards[0]),
        source_card=ctx.get("source_card"),
        source_object=ctx.get("source_object"),
    )
    if not holds(plan, bound):
        return True
    mark = plan.rules.timestamp
    before = {cid: {m.id for m in c.effects} for cid, c in plan.state.cards.items()}
    for instruction in inner:
        if not effects.PRIMITIVES[instruction["do"]](plan, ctx, instruction):
            raise AssertionError("Bound durations only wrap synchronous native primitives")
    written = delayed._relabel(plan, before, "for as long as the recorded condition holds")
    for made in plan.rules.effects:
        if made.timestamp > mark:
            made.duration = "permanent"
            made.duration_bound102 = bound.model_copy(deep=True)
            made.markers = [
                mid for cid, mids in written.items() if plan.oid(cid) in made.affected for mid in mids
            ]
    return True


def expire(plan: Plan) -> None:
    from app.rules import delayed

    ended = [
        e
        for e in plan.rules.effects
        if e.duration_bound102 is not None and not holds(plan, e.duration_bound102)
    ]
    if ended:
        delayed._end(plan, ended)


def pick_linked(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import context, effects
    from app.rules.plan import decide

    who = effects._cards(plan, ctx, "event")
    bound = DurationBound102(
        kind="attached",
        target_object=plan.oid(who[0]) if len(who) == 1 else "",
        source_card=ctx.get("source_card"),
        source_object=ctx.get("source_object"),
    )
    context.bind_objects(plan, ctx, "linked_copy102", [])
    if not holds(plan, bound):
        return True
    cards = [
        cid
        for cid in effects._cards(plan, ctx, e["who"])
        if plan.state.cards[cid].zone.endswith(":exile")
        and "Creature" in plan.ch(plan.state.cards[cid]).types
        and not plan.state.cards[cid].token
    ]
    if len(cards) <= 1:
        context.bind_objects(plan, ctx, "linked_copy102", cards)
        return True
    decide(
        plan,
        player=ctx["controller"],
        kind="choose_one",
        prompt=f"{ctx.get('name') or 'Equipment'}: choose a linked creature card to copy",
        options=[
            DecisionOption(id=cid, card_id=cid, label=plan.ch(plan.state.cards[cid]).name) for cid in cards
        ],
        resume={
            "step": "linked_copy102",
            "ctx": ctx,
            "bound": bound.model_dump(),
            "options": {cid: plan.oid(cid) for cid in cards},
        },
    )
    return False


def resume_linked(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import context, effects

    data, ctx = d.resume, d.resume["ctx"]
    card = plan.state.cards.get(chosen[0]) if len(chosen) == 1 else None
    if (
        card is not None
        and data["options"].get(card.id) == plan.oid(card)
        and card.zone.endswith(":exile")
        and "Creature" in plan.ch(card).types
        and holds(plan, DurationBound102.model_validate(data["bound"]))
    ):
        context.bind_objects(plan, ctx, "linked_copy102", [card.id])
    effects.continue_effects(plan, ctx)


PRIMITIVES = {"bound102": apply, "pick_linked_copy102": pick_linked}
RESUME = {"linked_copy102": resume_linked}
