"""Composed native effects using direct paid cards and explicit discard-result bindings."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.rules.plan import Plan

if TYPE_CHECKING:
    from app.game.rules_state import Decision
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText
    from app.rules.scripts import Definition


def native(text: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    return scripts.parse_effects(text)


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = re.sub(r"\s+", " ", body.strip())
    text = text.replace('except it has "Whenever ~ deals', 'except it has "Whenever this creature deals')
    replacements = {
        "Choose target player. They may discard up to X cards. Then they draw a card for each card discarded this way.": "Target player discards up to X cards. Then that player draws a card for each card discarded this way.",
    }
    if text in replacements:
        return native(replacements[text])
    scalar = {
        "~ deals X damage to each creature your opponents control, where X is the revealed card's mana value.": (
            "revealed",
            "mv",
            "~ deals X damage to each creature your opponents control.",
        ),
        "Target creature gets -X/-X until end of turn, where X is the revealed card's mana value.": (
            "revealed",
            "mv",
            "Target creature gets -X/-X until end of turn.",
        ),
        "~ deals 2 damage to any target. If the discarded card was multicolored, ~ deals 4 damage instead.": (
            "discarded",
            "multicolored",
            "~ deals X damage to any target.",
        ),
        "Put X +1/+1 counters on ~, where X is the exiled card's mana value.": (
            "exiled",
            "mv",
            "Put X +1/+1 counters on ~.",
        ),
    }
    if text in scalar:
        kind, mode, prototype = scalar[text]
        got = native(prototype)
        if got is None:
            return None
        return (
            [
                {
                    "do": "paid_hidden_effect",
                    "kind": kind,
                    "mode": mode,
                    "recipe": got[0],
                    "cost_source": "cost:" + kind,
                }
            ],
            got[1],
            False,
        )
    if (
        text
        == "~ deals damage equal to the total mana value of the discarded cards to each of up to X target creatures and/or planeswalkers."
    ):
        got = native("~ deals 1 damage to each of up to X target creatures and/or planeswalkers.")
        if got is None:
            return None
        return (
            [
                {
                    "do": "paid_hidden_effect",
                    "kind": "discarded",
                    "mode": "total_mv",
                    "recipe": got[0],
                    "cost_source": "cost:discarded",
                }
            ],
            got[1],
            False,
        )
    if (
        text
        == "Return target creature card from your graveyard to the battlefield. Put a +2/+2 counter on that creature if the exiled creature was a Thrull."
    ):
        got = native("Return target creature card from your graveyard to the battlefield.")
        assert got is not None
        es = got[0]
        es[0]["as"] = "soul_returned"
        return (
            [
                *es,
                {
                    "do": "paid_hidden_effect",
                    "kind": "exiled",
                    "mode": "thrull",
                    "cost_source": "cost:exiled",
                    "ref": "ref:soul_returned",
                },
            ],
            got[1],
            False,
        )
    if (
        text
        == "Discard any number of cards at random. Creatures you control get +1/+0 until end of turn for each card discarded this way."
    ):
        got = native("Creatures you control get +X/+0 until end of turn.")
        assert got is not None
        return (
            [
                {"do": "random_discard_number", "as": "random_discard"},
                {
                    "do": "discard_result_effect",
                    "mode": "recall",
                    "ref": "ref:random_discard",
                    "recipe": got[0],
                },
            ],
            None,
            False,
        )
    if (
        text
        == "Target creature gets +2/+0 until end of turn for each card discarded this way. Whenever that creature deals combat damage to a player this turn, you draw a card."
    ):
        got = native(
            "Target creature gets +X/+0 until end of turn. Whenever that creature deals combat damage to a player this turn, you draw a card."
        )
        assert got is not None
        return [{"do": "discard_event_effect", "mode": "pump_watch", "recipe": got[0]}], got[1], False
    if text == "You may sacrifice ~. If you do, return the discarded card from your graveyard to your hand.":
        got = native("You may sacrifice ~. If you do, draw a card.")
        assert got is not None
        got[0][-1] = {"do": "discard_event_effect", "mode": "return_gy"}
        return got
    if text == "Draw cards equal to its base power.":
        return [{"do": "draw_base_power"}], None, False
    if (
        text
        == '~ becomes a copy of the exiled creature, except it has "Whenever this creature deals combat damage to a player, draw cards equal to its base power."'
    ):
        from app.rules import copying

        exc = copying.parse_excepts(
            'it has "Whenever this creature deals combat damage to a player, draw cards equal to its base power."'
        )
        if exc is None:
            return None
        return (
            [
                {
                    "do": "paid_hidden_effect",
                    "kind": "exiled",
                    "mode": "copy_lki",
                    "cost_source": "cost:exiled",
                    "excepts": [exc.model_dump(mode="json")],
                }
            ],
            None,
            False,
        )
    if (
        text
        == "Discard X cards, then return a card from your graveyard to your hand for each card discarded this way. Exile ~."
    ):
        got = native("Return X cards from your graveyard to your hand.")
        assert got is not None
        return (
            [
                {"do": "discard", "who": "you", "n": {"x": 1}, "as": "recall_discard"},
                {
                    "do": "discard_result_effect",
                    "mode": "recall",
                    "ref": "ref:recall_discard",
                    "recipe": got[0],
                },
                {"do": "exile", "who": "self_stack"},
            ],
            None,
            False,
        )
    if text == "Discard any number of cards, then investigate twice for each card discarded this way.":
        got = native("Investigate X times.")
        assert got is not None
        return (
            [
                {"do": "discard", "who": "you", "n": 0, "upto": True, "as": "investigate_discard"},
                {
                    "do": "discard_result_effect",
                    "mode": "investigate",
                    "ref": "ref:investigate_discard",
                    "recipe": got[0],
                },
            ],
            None,
            False,
        )
    if (
        text
        == "Discard any number of cards. Target player reveals their hand, then you choose a nonland card from it for each card discarded this way. That player discards those cards."
    ):
        got = native(
            "Target player reveals their hand. You choose X nonland cards from it. That player discards those cards."
        )
        assert got is not None
        return (
            [
                {"do": "discard", "who": "you", "n": 0, "upto": True, "as": "rites_discard"},
                {
                    "do": "discard_result_effect",
                    "mode": "last_rites",
                    "ref": "ref:rites_discard",
                    "recipe": got[0],
                },
            ],
            got[1],
            False,
        )
    if (
        text
        == "Target player discards two cards. Put up to one land card discarded this way onto the battlefield tapped under your control."
    ):
        got = native("Target player discards two cards.")
        assert got is not None
        got[0][0]["as"] = "mind_discard"
        return (
            [*got[0], {"do": "discard_result_effect", "mode": "land", "ref": "ref:mind_discard"}],
            got[1],
            False,
        )
    if (
        text
        == "Each player discards a card. Each opponent who discarded a card that shares a card type with the card you discarded loses 3 life."
    ):
        return (
            [
                {"do": "discard", "who": "each_player", "n": 1, "as": "dread_discard"},
                {"do": "discard_result_effect", "mode": "shared_types", "ref": "ref:dread_discard"},
            ],
            None,
            False,
        )
    return None


def insert(ctx: dict[str, Any], es: list[dict[str, Any]]) -> bool:
    i = ctx["next"]
    ctx["effects"][i:i] = es
    return True


def paid(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, payment_card_facts
    from app.rules.paid_sacrifice_effects import legacy, replace_x

    facts = payment_card_facts.get(plan, ctx, e["kind"])
    if facts is None:
        return legacy(
            plan,
            ctx,
            "This older save did not retain the directly paid card characteristics. Apply this payment-dependent instruction by hand, then press Done.",
        )
    mode = e["mode"]
    if mode == "thrull":
        sid = ctx.get("stack_id")
        receipt = plan.rules.payments.get(plan.oid(sid)) if sid else None
        old = receipt.exiled_was if receipt else []
        ctx.setdefault("refs", {})["paid_exiled_old"] = {
            "kind": "objects",
            "objects": [
                {
                    "card": oid.rsplit(".", 1)[0],
                    "object_id": oid,
                    "zone": plan.rules.lki[oid].zone if oid in plan.rules.lki else None,
                }
                for oid in old
            ],
        }
        infos = context.infos(plan, ctx, "paid_exiled_old")
        if any("Thrull" in ch.subtypes for _, ch in infos):
            refs = context.refs(ctx).get(e["ref"].removeprefix("ref:"), {})
            context.refs(ctx)["soul_current"] = {
                "kind": "objects",
                "objects": refs.get("moved") or refs.get("objects") or [],
            }
            ids = [
                cid
                for cid in context.objects(plan, ctx, "soul_current")
                if plan.state.cards[cid].zone.endswith(":battlefield")
                and "Creature" in plan.ch(plan.state.cards[cid]).types
            ]
            context.bind_objects(plan, ctx, "soul_current", ids)
            return insert(ctx, [{"do": "add_counters", "who": "ref:soul_current", "kind": "+2/+2", "n": 1}])
        return True
    if mode == "copy_lki":
        sid = ctx.get("stack_id")
        receipt = plan.rules.payments.get(plan.oid(sid)) if sid else None
        old = receipt.exiled_was if receipt else []
        context.refs(ctx)["paid_exiled_old"] = {
            "kind": "objects",
            "objects": [
                {
                    "card": oid.rsplit(".", 1)[0],
                    "object_id": oid,
                    "zone": plan.rules.lki[oid].zone if oid in plan.rules.lki else None,
                }
                for oid in old
            ],
        }
        return insert(
            ctx,
            [
                {
                    "do": "become_copy",
                    "who": "self",
                    "with": "ref:paid_exiled_old",
                    "last_known": True,
                    "excepts": e["excepts"],
                }
            ],
        )
    n = (
        4
        if mode == "multicolored" and any(len(f.colors) > 1 for f in facts)
        else 2
        if mode == "multicolored"
        else int(sum(f.mana_value for f in facts))
    )
    recipe = replace_x(e["recipe"], n)
    if mode == "total_mv":
        for x in recipe:
            if x.get("do") == "damage":
                x["n"] = n
    return insert(ctx, recipe)


def discarded(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, selectors, this_way
    from app.rules.paid_sacrifice_effects import replace_x

    binding = context.refs(ctx).get(e["ref"].removeprefix("ref:"), {})
    n = this_way.count(
        plan, ctx, {"this_way": "discarded", "of": None, "ref_count": e["ref"].removeprefix("ref:")}
    )
    mode = e["mode"]
    if mode in ("recall", "investigate", "last_rites"):
        return insert(ctx, replace_x(e["recipe"], n * (2 if mode == "investigate" else 1)))
    refs = binding.get("moved") or binding.get("objects") or []
    current = e["ref"].removeprefix("ref:") + ":current"
    context.refs(ctx)[current] = {"kind": "objects", "objects": refs}
    ids = context.objects(plan, ctx, current)
    if mode == "land":
        ids = [cid for cid in ids if "Land" in plan.ch(plan.state.cards[cid]).types]
        context.bind_objects(plan, ctx, current, ids)
        return insert(
            ctx,
            [
                {
                    "do": "return_choice",
                    "who": "ref:" + current,
                    "sel": selectors.Selector(card=True, zones=()).key(),
                    "n": 1,
                    "upto": True,
                    "to": "battlefield",
                    "tapped": True,
                    "under": "you",
                    "random": False,
                    "label": "land card",
                }
            ],
        )
    if mode == "shared_types":
        own = set().union(
            *(
                plan.ch(plan.state.cards[c]).types
                for c in ids
                if plan.state.cards[c].owner == ctx["controller"]
            )
        )
        opponents = {
            plan.state.cards[c].owner
            for c in ids
            if plan.state.cards[c].owner != ctx["controller"]
            and own.intersection(plan.ch(plan.state.cards[c]).types)
        }
        return insert(ctx, [{"do": "lose_life", "who": "player:" + p, "n": 3} for p in sorted(opponents)])
    return True


PRIMITIVES = {"paid_hidden_effect": paid, "discard_result_effect": discarded}


def definition(ability: AbilityText, ch: Characteristics) -> Definition | None:
    from dataclasses import replace

    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if ability.kind == "spell":
        lead, body = "", text
    elif ability.kind == "activated" and ": " in text:
        cost_text, body = text.split(": ", 1)
        lead = cost_text + ": "
    elif " — " in text:
        chapter, body = text.split(" — ", 1)
        lead = chapter + " — "
    elif ability.kind == "triggered" and ", " in text:
        trigger, body = text.split(", ", 1)
        lead = trigger + ", "
    else:
        return None
    body = body[:1].upper() + body[1:]
    got = parse(body)
    if got is None:
        return None
    paid_effects = [e for e in got[0] if e.get("do") == "paid_hidden_effect"]
    if paid_effects:
        from app.rules import costs

        cost = (
            costs.spell_additional_cost(ch.abilities)
            if ability.kind == "spell"
            else costs.parse_ability_cost(ability.cost, card_name=ch.name)
            if ability.kind == "activated" and ability.cost
            else None
        )
        if cost is None or cost.either:
            return None
        for e in paid_effects:
            kinds = {
                "revealed": ("REVEAL_FROM_HAND",),
                "discarded": (costs.DISCARD,),
                "exiled": (
                    costs.EXILE,
                    costs.EXILE_FROM_GRAVEYARD,
                    "EXILE_FROM_HAND",
                    costs.EXILE_LIBRARY,
                ),
            }[e["kind"]]
            comps = [c for c in cost.components if c.kind in kinds]
            if len(comps) != 1 or (e["mode"] != "total_mv" and (comps[0].amount != 1 or comps[0].x)):
                return None
    # A native skeleton retains trigger/chapter/cost/target semantics, without
    # treating a locally defined X as an announced mana-cost variable.
    skeleton = "Draw a card."
    if got[1]:
        if body.startswith("Target creature gets"):
            skeleton = "Target creature gets -1/-1 until end of turn."
        elif body.startswith("Target creature gets +"):
            skeleton = "Target creature gets +1/+0 until end of turn."
        elif "any target" in body:
            skeleton = "~ deals 1 damage to any target."
        elif body.startswith("Target player discards") or body.startswith(
            "Discard any number of cards. Target player"
        ):
            skeleton = "Target player discards a card."
        else:
            return None
    base = scripts.define(replace(ability, text=lead + skeleton), ch)
    if base is None:
        return None
    base["effects"] = got[0]
    return base


def random_number(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.group_choice import NUMBER
    from app.rules.plan import decide

    n = len(plan.state.zones.get(ctx["controller"] + ":hand", []))
    decide(
        plan,
        player=ctx["controller"],
        kind="choose_one",
        prompt=f"Choose how many cards to discard at random (0–{n})",
        options=[DecisionOption(id=NUMBER, label="Type a number ≥ 0", group="number")],
        resume={"step": "hidden_random_number", "ctx": ctx, "as": e["as"], "max": n},
    )
    return False


def resume_random(plan: Plan, d: Decision, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    if d.resume is None:
        raise ValueError("A random-discard continuation needs its saved context")
    n = int(chosen[0])
    if n > d.resume["max"]:
        raise ActionError("Choose no more cards than your hand contains")
    ctx = d.resume["ctx"]
    insert(ctx, [{"do": "discard", "who": "you", "n": n, "random": True, "as": d.resume["as"]}])
    effects.continue_effects(plan, ctx)


def event_effect(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context
    from app.rules.paid_sacrifice_effects import replace_x

    if e["mode"] == "pump_watch":
        n = len(context.refs(ctx).get("event", {}).get("objects", []))
        if not n:
            n = len((ctx.get("event") or {}).get("objects") or [])
        return insert(ctx, replace_x(e["recipe"], 2 * n))
    from app.rules import discarded_references

    ids = [
        cid
        for cid in discarded_references.objects(plan, ctx, "event.new")
        if plan.state.cards[cid].zone == ctx["controller"] + ":graveyard"
    ]
    context.bind_objects(plan, ctx, "discard_return", ids)
    return insert(ctx, [{"do": "return_card", "who": "ref:discard_return", "to": "hand"}])


PRIMITIVES.update({"random_discard_number": random_number, "discard_event_effect": event_effect})
RESUME = {"hidden_random_number": resume_random}


def draw_base_power(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import values
    from app.rules.paid_sacrifice_effects import legacy

    src = plan.state.cards.get(ctx.get("source_card") or "")
    if src is None or plan.oid(src) != ctx.get("source_object") or not src.zone.endswith(":battlefield"):
        snap = plan.rules.lki.get(ctx.get("source_object") or "")
        if snap is not None and snap.base_power is None:
            return legacy(
                plan,
                ctx,
                "This older save did not retain the departed creature’s base power. Draw the appropriate number of cards by hand, then press Done.",
            )
    return insert(
        ctx, [{"do": "draw", "who": "you", "n": values.evaluate(plan, ctx, {"base_power": "self"})}]
    )


PRIMITIVES["draw_base_power"] = draw_base_power
