"""Original damage/death objects, deferred returns, and the original source's loss."""

from __future__ import annotations

from dataclasses import replace
from typing import Any


def loss_effects() -> list[dict[str, Any]]:
    from app.rules import delayed

    result = delayed.wrap_when(
        [{"do": "sacrifice", "who": "ref:returned105"}],
        {"kind": "event", "event": "lose_control", "open": True},
        who="self",
    )
    # Seraph's official ruling: a source already controlled by someone else may
    # later be regained and then lost. A departed original creates no watcher.
    result[0]["watch_foreign105"] = True
    return result


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import context, delayed, scripts

    text = scripts.self_text(ability.text, ch.name)
    krov = "At the beginning of each end step, if a creature dealt damage by ~ this turn died, put that card onto the battlefield under your control. Sacrifice it when you lose control of ~."
    seraph = "Whenever a creature dealt damage by ~ this turn dies, put that card onto the battlefield under your control at the beginning of the next end step. Sacrifice the creature when you lose control of ~."
    if text == krov:
        native = scripts.define(replace(ability, text="At the beginning of each end step, draw a card."), ch)
        assert native is not None
        return {
            **native,
            "if": {"damage_death105": True},
            "effects": [{"do": "return_damaged105"}, *loss_effects()],
        }
    if text == seraph:
        native = scripts.define(
            replace(ability, text="Whenever a creature dealt damage by ~ this turn dies, draw a card."), ch
        )
        assert native is not None
        cond = {**native["cond"], "damaged_by_exact105": True}
        cond.pop("damaged_by_self")
        inner = [
            {
                "do": "return_card",
                "who": context.EVENT_NEW,
                "to": "battlefield",
                "under": "you",
                "as": "returned105",
            },
            *loss_effects(),
        ]
        return {
            **native,
            "cond": cond,
            "effects": delayed.wrap_when(inner, {"kind": "step", "step": "end", "whose": "next"}),
        }
    return None


def departures(plan: Any, ctx: dict[str, Any]) -> list[Any]:
    from app.rules import history

    log = history.log_for(plan)
    victims = {
        f.object_id
        for f in log.facts
        if f.kind == "damaged" and f.source == ctx.get("source_object") and f.amount > 0
    }
    return [
        x
        for x in log.left
        if x.object_id in victims
        and x.to == "graveyard"
        and "Creature"
        in (
            x.types
            if x.types is not None
            else (plan.rules.lki[x.object_id].types if x.object_id in plan.rules.lki else [])
        )
    ]


def return_damaged(plan: Any, ctx: dict[str, Any], effect: Any) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import context
    from app.rules.plan import decide

    dead = departures(plan, ctx)
    if any(
        x.new_object_id105 is None
        and not (plan.rules.lki.get(x.object_id) and plan.rules.lki[x.object_id].is_token)
        for x in dead
    ):
        decide(
            plan,
            player=ctx["controller"],
            kind="manual_resolution",
            prompt="This older save does not identify the original cards in the graveyard. Resolve this return and its later sacrifice condition by hand, then press Done.",
            options=[DecisionOption(id="done", label="Done")],
            resume={"step": "vampire_returns105_legacy", "ctx": ctx},
        )
        return False
    cards = [
        x.card
        for x in dead
        if x.card in plan.state.cards
        and plan.state.cards[x.card].zone.endswith(":graveyard")
        and plan.oid(x.card) == x.new_object_id105
    ]
    context.bind_objects(plan, ctx, "dead105", cards)
    ctx["effects"][ctx["next"] : ctx["next"]] = [
        {"do": "return_card", "who": "ref:dead105", "to": "battlefield", "under": "you", "as": "returned105"}
    ]
    return True


def resume(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    # The legacy return was deliberately done by hand. Do not infer a cohort for
    # its loss watcher from the current battlefield.
    ctx = d.resume["ctx"]
    ctx["next"] = len(ctx["effects"])
    continue_effects(plan, ctx)


PRIMITIVES = {"return_damaged105": return_damaged}
RESUME = {"vampire_returns105_legacy": resume}


def damage_match(plan: Any, victim: str | None, source: str) -> bool:
    from app.rules import history

    return victim is not None and any(
        f.kind == "damaged" and f.object_id == victim and f.source == source and f.amount > 0
        for f in history.log_for(plan).facts
    )
