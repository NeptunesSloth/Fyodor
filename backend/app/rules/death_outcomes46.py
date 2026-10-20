"""Exact death outcomes follow the new graveyard object, never a physical successor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if (
        text
        == "When ~ dies, exile it if it had a death counter on it. Otherwise, return it to the battlefield under your control and put a death counter on it."
    ):
        base = scripts.define(replace(ability, text="When ~ dies, draw a card."), ch)
        return {**base, "effects": [{"do": "phoenix_death47"}]} if base else None
    if (
        text
        == "When ~ dies, exile it, then return the top creature card of your graveyard to the battlefield."
    ):
        base = scripts.define(replace(ability, text="When ~ dies, draw a card."), ch)
        return (
            {**base, "effects": [{"do": "exile_dead_source46"}, {"do": "mistmoon_top46"}]} if base else None
        )
    if (
        text
        == 'When ~ dies, create X 1/1 black Rat creature tokens with "This token can\'t block," where X is the amount of damage dealt to it this turn.'
    ):
        base = scripts.define(replace(ability, text="When ~ dies, draw a card."), ch)
        return {**base, "effects": [{"do": "tangled_rats46"}]} if base else None
    if (
        text
        == "When ~ dies, each creature that dealt damage to it this turn has base power and toughness 0/2."
    ):
        base = scripts.define(replace(ability, text="When ~ dies, draw a card."), ch)
        return {**base, "effects": [{"do": "brine_damagers46"}]} if base else None
    if (
        text
        == "When ~ dies, exile it and each other player creates a 3/3 black Angel creature token with flying."
    ):
        shell = scripts.define(replace(ability, text="When ~ dies, draw a card."), ch)
        tokens = scripts.parse_effects(
            "Each other player creates a 3/3 black Angel creature token with flying."
        )
        assert tokens is not None
        return {**shell, "effects": [{"do": "exile_dead_source46"}, *tokens[0]]} if shell else None
    if text == "When ~ dies, target land becomes a Swamp. Exile this card.":
        base = scripts.define(replace(ability, text="When ~ dies, target land becomes a Swamp."), ch)
        return {**base, "effects": [*base["effects"], {"do": "exile_dead_source46"}]} if base else None
    return None


def exile_original(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.rules import context

    at = ctx["next"]
    ctx["effects"] = [
        *ctx["effects"][:at],
        {"do": "exile", "who": "ref:" + context.EVENT_NEW, "from_zone": "graveyard"},
        *ctx["effects"][at:],
    ]
    return True


PRIMITIVES = {"exile_dead_source46": exile_original}


def brine_damagers(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import context, history
    from app.rules.plan import decide

    source = ctx.get("source_object")
    if not isinstance(source, str) or not source:
        decide(
            plan,
            player=ctx["controller"],
            kind="manual_resolution",
            prompt="This save lacks the original damaged object. Set the appropriate creatures to base 0/2 manually.",
            options=[DecisionOption(id="done", label="Done")],
            resume={"step": "death46_unknown_history", "ctx": ctx},
        )
        return False
    damagers = {
        f.source
        for f in history.log_for(plan).facts
        if f.kind == "damaged" and f.amount > 0 and f.object_id == source and f.source is not None
    }
    cards = [
        card.id
        for card in plan.state.cards.values()
        if card.zone.endswith(":battlefield")
        and plan.in_game(card)
        and plan.ch(card).is_creature
        and plan.oid(card) in damagers
    ]
    context.bind_objects(plan, ctx, "brine46_damagers", cards)
    at = ctx["next"]
    ctx["effects"] = [
        *ctx["effects"][:at],
        {"do": "become", "who": "ref:brine46_damagers", "types": [], "p": 0, "t": 2, "duration": "permanent"},
        *ctx["effects"][at:],
    ]
    return True


def unknown_history_done(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    if chosen != ["done"]:
        raise ActionError("Complete the manual resolution")
    effects.continue_effects(plan, d.resume["ctx"])


def tangled_rats(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import history, scripts
    from app.rules.plan import decide

    source = ctx.get("source_object")
    if not isinstance(source, str) or not source:
        decide(
            plan,
            player=ctx["controller"],
            kind="manual_resolution",
            prompt="This save lacks the original damaged object. Create the appropriate Rat tokens manually.",
            options=[DecisionOption(id="done", label="Done")],
            resume={"step": "death46_unknown_history", "ctx": ctx},
        )
        return False
    damage = sum(
        fact.amount
        for fact in history.log_for(plan).facts
        if fact.kind == "damaged" and fact.amount > 0 and fact.object_id == source
    )
    parsed = scripts.parse_effects('Create 1 1/1 black Rat creature token with "This token can\'t block."')
    assert parsed is not None
    tokens = [{**token, "n": damage} for token in parsed[0]]
    at = ctx["next"]
    ctx["effects"] = [*ctx["effects"][:at], *tokens, *ctx["effects"][at:]]
    return True


PRIMITIVES["brine_damagers46"] = brine_damagers
PRIMITIVES["tangled_rats46"] = tangled_rats
RESUME: dict[str, Callable[[Plan, Any, list[str]], None]] = {"death46_unknown_history": unknown_history_done}


def mistmoon_top(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.game.state import zone_key
    from app.rules import context, graveyard_order

    if graveyard_order.offer(plan):
        decision = plan.rules.decision
        assert decision is not None and decision.resume is not None
        decision.resume.update(step="death46_graveyard_order", death_ctx=ctx)
        return False
    pile = plan.state.zones.get(zone_key(ctx["controller"], "graveyard"), [])
    top = next((cid for cid in reversed(pile) if plan.ch(plan.state.cards[cid]).is_creature), None)
    if top is not None:
        context.bind_objects(plan, ctx, "mistmoon46_top", [top])
        at = ctx["next"]
        ctx["effects"] = [
            *ctx["effects"][:at],
            {
                "do": "return_card",
                "who": "ref:mistmoon46_top",
                "to": "battlefield",
                "under": "you",
                "tapped": False,
            },
            *ctx["effects"][at:],
        ]
    return True


def resume_graveyard_order(plan: Plan, decision: Any, chosen: list[str]) -> None:
    from app.rules import effects, graveyard_order

    graveyard_order.resume(plan, decision, chosen)
    ctx = decision.resume["death_ctx"]
    if mistmoon_top(plan, ctx, {}):
        effects.continue_effects(plan, ctx)


PRIMITIVES["mistmoon_top46"] = mistmoon_top
RESUME["death46_graveyard_order"] = resume_graveyard_order


def phoenix_death(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import context
    from app.rules.plan import decide

    source = ctx.get("source_object")
    snapshot = plan.rules.lki.get(source) if isinstance(source, str) else None
    if snapshot is None:
        snapshot = next(
            (
                context.snapshot(plan, ref)
                for ref in context._object_refs(ctx, context.EVENT)
                if ref.object_id == source
            ),
            None,
        )
    if snapshot is None:
        decide(
            plan,
            player=ctx["controller"],
            kind="manual_resolution",
            prompt="This save lacks the dying Phoenix's counters. Resolve its death ability manually.",
            options=[DecisionOption(id="done", label="Done")],
            resume={"step": "death46_unknown_history", "ctx": ctx},
        )
        return False
    follow: list[dict[str, Any]]
    if snapshot.counters.get("death", 0):
        follow = [{"do": "exile_dead_source46"}]
    else:
        follow = [
            {
                "do": "return_card",
                "who": "ref:" + context.EVENT_NEW,
                "to": "battlefield",
                "under": "you",
                "tapped": False,
                "as": "phoenix47_returned",
            },
            {"do": "add_counters", "who": "ref:phoenix47_returned", "kind": "death", "n": 1},
        ]
    at = ctx["next"]
    ctx["effects"] = [*ctx["effects"][:at], *follow, *ctx["effects"][at:]]
    return True


PRIMITIVES["phoenix_death47"] = phoenix_death
