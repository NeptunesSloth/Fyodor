"""Bounded missing modal clauses using native targets, counters, rules and choices."""

from __future__ import annotations

from typing import Any


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts, selectors

    if body == "Put two +1/+1 counters on up to one creature. It gains lifelink until end of turn.":
        # This choice is deliberately not a target and is made while resolving.
        return [{"do": "gix_creature101", "as": "gix101"}], None, False
    if (
        body
        == "Put a +1/+1 counter on target suspected creature you control. You may have it become no longer suspected."
    ):
        base = scripts.parse_effects("Put a +1/+1 counter on target creature you control.")
        assert base is not None
        return (
            [
                *base[0],
                {
                    "do": "optional_payment",
                    "who": "you",
                    "cost": "",
                    "ask": "Have it become no longer suspected",
                    "bind": "unsuspect101",
                },
                {"do": "only_if", "cond": {"succeeded": "unsuspect101"}, "skip": 1},
                {"do": "unsuspect100c", "who": "target"},
            ],
            selectors.Selector(types=("Creature",), controller="you", extras=("suspected",)).key(),
            False,
        )
    if (
        body
        == "Target planeswalker you control deals damage equal to its loyalty to target creature or planeswalker an opponent controls."
    ):
        base = scripts.parse_effects(
            "Target creature you control deals damage equal to its power to target creature or planeswalker an opponent controls."
        )
        assert base is not None and isinstance(base[1], list) and len(base[0]) == 1
        groups = [
            {**base[1][0], "what": selectors.Selector(types=("Planeswalker",), controller="you").key()},
            base[1][1],
        ]
        return [{**base[0][0], "n": {"counters": "loyalty", "on": "target:0"}}], groups, False
    if (
        body
        == "Permanents you control can't be the targets of blue or black spells your opponents control this turn."
    ):
        return (
            [
                {
                    "do": "restrict",
                    "who": selectors.Selector(controller="you").key(),
                    "rules": ["untargetable_opp_spells:UB"],
                }
            ],
            None,
            False,
        )
    return None


def gix_choice(plan: Any, ctx: Any, effect: Any) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import context, selectors
    from app.rules.plan import decide

    choices = selectors.candidates(
        plan, selectors.Selector(types=("Creature",)), ctx["controller"], ctx.get("source_card")
    )
    if not choices:
        return True
    refs = {
        cid: ref.model_dump(mode="json") for cid in choices if (ref := context.ref_of(plan, cid)) is not None
    }
    decide(
        plan,
        player=ctx["controller"],
        kind="choose_cards",
        prompt="Choose up to one creature for counters and lifelink",
        options=[
            DecisionOption(id=cid, label=plan.state.cards[cid].name or "Creature", card_id=cid)
            for cid in choices
        ],
        min_choices=0,
        max_choices=1,
        resume={"step": "gix_creature101", "ctx": ctx, "e": effect, "originals": refs},
    )
    return False


def resume_gix(plan: Any, decision: Any, chosen: list[str]) -> None:
    from app.game.rules_state import ObjectRef
    from app.rules import context, effects

    data, ctx = decision.resume, decision.resume["ctx"]
    if chosen:
        cid = chosen[0]
        ref = ObjectRef.model_validate(data["originals"][cid])
        card = plan.state.cards.get(cid)
        if (
            card is not None
            and plan.oid(card) == ref.object_id
            and ref.zone is not None
            and card.zone.rsplit(":", 1)[-1] == ref.zone.rsplit(":", 1)[-1]
            and plan.ch(card).is_creature
        ):
            key = data["e"]["as"]
            context.bind_objects(plan, ctx, key, [cid])
            at = ctx["next"]
            ctx["effects"][at:at] = [
                {"do": "add_counters", "who": "ref:" + key, "kind": "+1/+1", "n": 2},
                {"do": "grant", "who": "ref:" + key, "keywords": ["lifelink"]},
            ]
    effects.continue_effects(plan, ctx)


PRIMITIVES = {"gix_creature101": gix_choice}
RESUME = {"gix_creature101": resume_gix}
