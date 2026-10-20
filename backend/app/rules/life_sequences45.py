"""Exact life instructions composed from native independent target groups."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if (
        text
        == "When ~ dies, you may gain 1 life for each creature card in your graveyard. If you do, exile this card from your graveyard."
    ):
        base = scripts.define(replace(ability, text="When ~ dies, you gain 1 life."), ch)
        return {**base, "effects": [{"do": "spider_life_cost45"}]} if base else None
    if text != "Target player gains 5 life, ~ deals 5 damage to any target, then you draw five cards.":
        return None
    return scripts.define(
        replace(ability, text="Target player gains 5 life. ~ deals 5 damage to any target. Draw five cards."),
        ch,
    )


def spider_start(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import cant_gain
    from app.rules.plan import decide

    # CR119.7 forbids paying a life-gain cost. A replacement (including a loss
    # instead) does not invalidate acceptance of a payable cost, CR118.12.
    if cant_gain.why_not(plan, ctx["controller"]) is not None:
        return True
    amount = sum(
        plan.ch(plan.state.cards[cid]).is_creature
        for cid in plan.state.zones.get(ctx["controller"] + ":graveyard", [])
        if not plan.state.cards[cid].is_token and plan.state.cards[cid].card_id is not None
    )
    decide(
        plan,
        player=ctx["controller"],
        kind="confirm",
        prompt=f"Gain {amount} life and exile this card from your graveyard?",
        options=[DecisionOption(id="yes", label="Yes"), DecisionOption(id="no", label="No")],
        resume={"step": "spider_life_cost45", "ctx": ctx, "amount": amount},
    )
    return False


def spider_resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import cant_gain, context, effects

    if chosen not in (["yes"], ["no"]):
        raise ActionError("Choose whether to pay the life-gain cost")
    ctx = d.resume["ctx"]
    if chosen == ["yes"]:
        if cant_gain.why_not(plan, ctx["controller"]) is not None:
            raise ActionError("You cannot gain life to pay this cost")
        context.refs(ctx)["spider45_source"] = {
            "kind": "objects",
            "objects": [
                ref.model_dump(mode="json")
                for ref in context._object_refs(ctx, context.EVENT_NEW)
                if ref.zone == ctx["controller"] + ":graveyard"
            ],
        }
        at = ctx["next"]
        ctx["effects"] = [
            *ctx["effects"][:at],
            {"do": "gain_life", "who": "you", "n": d.resume["amount"]},
            {"do": "exile", "who": "ref:spider45_source", "from_zone": "graveyard"},
            *ctx["effects"][at:],
        ]
    effects.continue_effects(plan, ctx)


PRIMITIVES = {"spider_life_cost45": spider_start}
RESUME = {"spider_life_cost45": spider_resume}
