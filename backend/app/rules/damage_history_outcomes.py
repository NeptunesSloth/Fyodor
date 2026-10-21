"""Resolution values read from native turn history and exact instruction receipts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.rules import context, selectors

if TYPE_CHECKING:
    from app.rules.plan import Plan

BODIES = {
    "~ deals damage to target creature equal to the damage already dealt to it this turn": (
        "whipkeeper",
        "Target creature gets +1/+1 until end of turn.",
    ),
    "Destroy X target artifacts. ~ deals damage to each player equal to the number of artifacts they controlled that were put into a graveyard this way": (
        "builders",
        "Destroy X target artifacts.",
    ),
    "~ deals X damage to target opponent or planeswalker and half X damage, rounded up, to you, where X is the number of Mountains you control": (
        "eternal",
        "~ deals 1 damage to target opponent or planeswalker.",
    ),
    "~ deals X damage divided evenly, rounded down, among all creatures target opponent controls": (
        "catapult",
        "Target opponent draws a card.",
    ),
    "~ deals damage to target creature equal to the number of creatures you control in excess of the number of creatures target opponent controls": (
        "superior",
        "Target creature gets +1/+1 until end of turn. Target opponent draws a card.",
    ),
    "Target creature's controller reveals a card at random from their hand. ~ deals damage to that creature and that player equal to the revealed card's mana value": (
        "friendly",
        "Target creature gets +1/+1 until end of turn.",
    ),
    "You may put target creature card from your graveyard on top of your library. If you do, ~ deals damage equal to that card's power to target creature": (
        "reckoning",
        "Return target creature card from your graveyard to your hand. Target creature gets +1/+1 until end of turn.",
    ),
    "Tap target untapped creature you control. If you do, it deals damage equal to its power to target attacking or blocking creature an opponent controls": (
        "spirit",
        "Tap target untapped creature you control. ~ deals 1 damage to target attacking or blocking creature an opponent controls.",
    ),
    "~ deals damage equal to the tapped creature's power to target attacking or blocking creature with flying": (
        "sling",
        "~ deals 1 damage to target attacking or blocking creature with flying.",
    ),
    "Choose any target, then mill three cards. ~ deals damage to that permanent or player equal to the greatest mana value among the milled cards": (
        "heretic",
        "~ deals 1 damage to any target.",
    ),
}


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    item = BODIES.get(body.strip().rstrip("."))
    if item is None:
        return None
    mode, prototype = item
    parsed = scripts.parse_effects(prototype)
    if parsed is None:
        return None
    return [{"do": "damage_history_outcome", "mode": mode}], parsed[1], False


def insert(ctx: dict[str, Any], steps: list[dict[str, Any]]) -> bool:
    ctx["effects"][ctx["next"] : ctx["next"]] = steps
    return True


def batch(ctx: dict[str, Any], steps: list[dict[str, Any]]) -> bool:
    for e in steps[:-1]:
        e["with_next"] = True
    return insert(ctx, steps)


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, history, values

    mode = e["mode"]
    creatures = [
        c
        for c in plan.state.cards.values()
        if c.zone.endswith(":battlefield") and "Creature" in plan.ch(c).types
    ]
    if mode in ("trumpet", "monsoon"):
        players = effects._players(plan, ctx, "event_player")
        attacked = {oid for ids in history.log_for(plan).attackers.values() for oid in ids}
        ids = [
            c.id
            for c in plan.state.cards.values()
            if c.zone.endswith(":battlefield")
            and c.controller in players
            and not c.tapped
            and (
                ("Creature" in plan.ch(c).types and plan.oid(c) not in attacked)
                if mode == "trumpet"
                else "Island" in plan.ch(c).subtypes
            )
        ]
        context.bind_objects(plan, ctx, "history_to_tap", ids)
        return insert(
            ctx,
            [
                {"do": "tap", "who": "ref:history_to_tap"},
                {"do": "damage", "who": "event_player", "n": len(ids)},
            ],
        )
    if mode == "curse":
        players = effects._players(plan, ctx, "event_player")
        n = sum(
            c.zone.endswith(":battlefield")
            and c.attached_player in players
            and "Curse" in plan.ch(c).subtypes
            for c in plan.state.cards.values()
        )
        return insert(ctx, [{"do": "damage", "who": "event_player", "n": n}])
    if mode == "hunger":
        players = effects._players(plan, ctx, "event_player")
        if not players:
            return True
        context.refs(ctx)["history_hunger_host"] = {
            "kind": "objects",
            "objects": [r.model_dump(mode="json") for r in context._object_refs(ctx, "event", was=True)],
        }
        ctx.setdefault("resolution_cost_exclusions", []).append(
            {"payer": players[0], "who": "ref:history_hunger_host"}
        )
        return insert(
            ctx,
            [
                {
                    "do": "optional_payment",
                    "who": "event_player",
                    "cost": "Sacrifice a creature",
                    "bind": "history_hunger_paid",
                },
                {"do": "only_if", "cond": {"not": {"succeeded": "history_hunger_paid"}}, "skip": 1},
                {"do": "damage", "who": "event_player", "n": {"power": "ref:history_hunger_host"}},
            ],
        )
    if mode == "tuktuk":
        context.bind_objects(plan, ctx, "history_tuktuk_target", effects._cards(plan, ctx, "target"))
        return insert(
            ctx,
            [
                {"do": "destroy", "who": "target", "as": "history_destroyed"},
                {"do": "damage_history_finish", "mode": mode},
            ],
        )
    if mode == "sentinel":
        refs = context._object_refs(ctx, "event", was=True)
        oid = refs[0].object_id if refs else None
        n = 1
        for cast in history.log_for(plan).casts:
            if cast.object_id == oid:
                break
            if set(cast.types) & {"Instant", "Sorcery"}:
                n += 1
        return insert(ctx, [{"do": "damage", "who": "target", "n": n}])
    if mode == "electryte":
        return insert(
            ctx,
            [
                {
                    "do": "damage",
                    "who": selectors.Selector(types=("Creature",), blocking=True).key(),
                    "n": {"power": "self"},
                }
            ],
        )
    if mode == "growth":
        players = effects._players(plan, ctx, "event_player")
        ids = effects._cards(plan, ctx, "self")
        snap = plan.rules.lki.get(ctx.get("source_object") or "")
        n = (
            plan.state.cards[ids[0]].counters.get("growth", 0)
            if ids
            else (snap.counters.get("growth", 0) if snap else 0)
        )
        before = {pid: history.log_for(plan).drew.get(pid, 0) for pid in players}
        return insert(
            ctx,
            [
                {"do": "draw", "who": "event_player", "n": n},
                {"do": "damage_history_finish", "mode": mode, "before": before},
            ],
        )
    if mode == "whipkeeper":
        damaged_oids = {plan.oid(cid) for cid in effects._cards(plan, ctx, "target")}
        n = sum(
            f.amount
            for f in history.log_for(plan).facts
            if f.kind == "damaged" and f.object_id in damaged_oids
        )
        return insert(ctx, [{"do": "damage", "who": "target", "n": n}])
    if mode == "eternal":
        n = sum(
            c.zone.endswith(":battlefield")
            and c.controller == ctx["controller"]
            and "Mountain" in plan.ch(c).subtypes
            for c in plan.state.cards.values()
        )
        return batch(
            ctx,
            [{"do": "damage", "who": "target", "n": n}, {"do": "damage", "who": "you", "n": (n + 1) // 2}],
        )
    if mode == "catapult":
        players = effects._players(plan, ctx, "target")
        ids = [c.id for c in creatures if c.controller in players]
        context.bind_objects(plan, ctx, "history_catapult", ids)
        return (
            insert(
                ctx,
                [
                    {
                        "do": "damage",
                        "who": "ref:history_catapult",
                        "n": values.evaluate(plan, ctx, {"x": 1}) // len(ids),
                    }
                ],
            )
            if ids
            else True
        )
    if mode == "superior":
        players = effects._players(plan, ctx, "target:1")
        if not players:
            return True
        n = max(
            0,
            sum(c.controller == ctx["controller"] for c in creatures)
            - sum(c.controller == players[0] for c in creatures),
        )
        return insert(ctx, [{"do": "damage", "who": "target:0", "n": n}])
    if mode == "sling":
        return insert(ctx, [{"do": "damage", "who": "target", "n": {"power": "cost:tapped"}}])
    if mode == "builders":
        return insert(
            ctx,
            [
                {"do": "destroy", "who": "target:0", "as": "history_destroyed"},
                {"do": "damage_history_finish", "mode": mode},
            ],
        )
    if mode == "heretic":
        return insert(
            ctx,
            [
                {"do": "mill", "who": "you", "n": 3, "as": "history_milled"},
                {"do": "damage_history_finish", "mode": mode},
            ],
        )
    if mode == "friendly":
        context.bind_objects(plan, ctx, "history_friendly_target", effects._cards(plan, ctx, "target"))
        return insert(
            ctx,
            [
                {
                    "do": "reveal_random",
                    "who": "ref:history_friendly_target.controller",
                    "n": 1,
                    "as": "history_random",
                },
                {"do": "damage_history_finish", "mode": mode},
            ],
        )
    if mode == "reckoning":
        if not effects._cards(plan, ctx, "target:0"):
            return True
        n = values.evaluate(plan, ctx, {"power": "target:0"})
        return insert(
            ctx,
            [
                {"do": "may_rest", "who": "you"},
                {"do": "to_library", "who": "target:0", "place": "top", "as": "history_reckoned"},
                {"do": "damage_history_finish", "mode": mode, "amount": n},
            ],
        )
    if mode == "spirit":
        return insert(
            ctx,
            [
                {"do": "tap", "who": "target:0", "did": "history_tapped"},
                {"do": "only_if", "cond": {"succeeded": "history_tapped"}, "skip": 1},
                {"do": "damage", "src": "target:0", "who": "target:1", "n": {"power": "target:0"}},
            ],
        )
    return True


def finish(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import this_way, values

    mode = e["mode"]
    if mode == "tuktuk":
        if not this_way.count(plan, ctx, {"this_way": "died", "of": None, "ref_count": "history_destroyed"}):
            return True
        n = len(
            selectors.candidates(
                plan,
                selectors.Selector(subtypes=("Ally",), controller="you"),
                ctx["controller"],
                ctx.get("source_card"),
            )
        )
        return insert(ctx, [{"do": "damage", "who": "ref:history_tuktuk_target.controller", "n": n}])
    if mode == "growth":
        from app.rules import history

        return batch(
            ctx,
            [
                {
                    "do": "damage",
                    "who": "player:" + pid,
                    "n": max(0, history.log_for(plan).drew.get(pid, 0) - before),
                }
                for pid, before in e["before"].items()
            ],
        )
    if mode == "builders":
        counts = this_way.by_controller(
            plan, ctx, {"this_way": "died", "of": None, "ref_count": "history_destroyed"}
        )
        return batch(ctx, [{"do": "damage", "who": "player:" + pid, "n": n} for pid, n in counts.items()])
    if mode == "heretic":
        amounts = []
        for i, cid in enumerate(context.objects(plan, ctx, "history_milled")):
            name = "history_milled_" + str(i)
            context.bind_objects(plan, ctx, name, [cid])
            amounts.append(values.evaluate(plan, ctx, {"mana_value": "ref:" + name}))
        return insert(ctx, [{"do": "damage", "who": "target", "n": max(amounts, default=0)}])
    if mode == "friendly":
        n = values.evaluate(plan, ctx, {"mana_value": "ref:history_random"})
        return batch(
            ctx,
            [
                {"do": "damage", "who": "ref:history_friendly_target", "n": n},
                {"do": "damage", "who": "ref:history_friendly_target.controller", "n": n},
            ],
        )
    if mode == "reckoning":
        return insert(ctx, [{"do": "damage", "who": "target:1", "n": e["amount"]}])
    return True


PRIMITIVES = {"damage_history_outcome": run, "damage_history_finish": finish}

TRIGGER_BODIES = {
    "At the beginning of each player's end step, tap all untapped creatures that player controls that didn't attack this turn. ~ deals damage to the player equal to the number of creatures tapped this way.": (
        "trumpet",
        "At the beginning of each player's end step, you gain 1 life.",
    ),
    "At the beginning of each player's end step, tap all untapped Islands that player controls and ~ deals X damage to the player, where X is the number of Islands tapped this way.": (
        "monsoon",
        "At the beginning of each player's end step, you gain 1 life.",
    ),
    "Whenever an instant or sorcery spell is cast during your turn, ~ deals damage to any target equal to 1 plus the number of instant and sorcery spells cast before that spell this turn.": (
        "sentinel",
        "Whenever a player casts an instant or sorcery spell during your turn, ~ deals 1 damage to any target.",
    ),
    "At the beginning of enchanted player's upkeep, ~ deals damage to that player equal to the number of Curses attached to them.": (
        "curse",
        "At the beginning of enchanted player's upkeep, you gain 1 life.",
    ),
    "At the beginning of the upkeep of enchanted creature's controller, ~ deals damage equal to that creature's power to that player unless they sacrifice another creature of their choice.": (
        "hunger",
        "At the beginning of the upkeep of enchanted creature's controller, you gain 1 life.",
    ),
    "Whenever ~ or another Ally you control enters, you may destroy target artifact. If that artifact is put into a graveyard this way, ~ deals damage to that artifact's controller equal to the number of Allies you control.": (
        "tuktuk",
        "Whenever ~ or another Ally you control enters, you may destroy target artifact.",
    ),
    "Whenever ~ deals damage to a creature or opponent, ~ deals that much damage to you.": (
        "flesh",
        "Whenever ~ deals damage, you gain 1 life.",
    ),
    "Whenever a red creature or spell deals damage, ~ deals that much damage to that creature's or spell's controller.": (
        "justice",
        "Whenever a red source deals damage to one or more permanents and/or players, you gain 1 life.",
    ),
    "Whenever ~ deals combat damage to defending player, it deals damage equal to its power to each blocking creature.": (
        "electryte",
        "Whenever ~ deals combat damage to a player, you gain 1 life.",
    ),
    "At the beginning of each opponent's draw step, that player draws an additional card for each growth counter on ~, then ~ deals damage to the player equal to the number of cards they drew this way.": (
        "growth",
        "At the beginning of each opponent's draw step, you gain 1 life.",
    ),
}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import scripts

    if ability.kind == "spell":
        parsed = parse(scripts.self_text(ability.text, ch.name))
        if parsed is None:
            return None
        body_item = BODIES[scripts.self_text(ability.text, ch.name).strip().rstrip(".")]
        native_spell = scripts.define(replace(ability, text=body_item[1]), ch)
        return {**native_spell, "effects": parsed[0]} if native_spell else None
    if ability.kind != "triggered":
        return None
    item = TRIGGER_BODIES.get(scripts.self_text(ability.text, ch.name))
    if item is None:
        return None
    mode, prototype = item
    native = scripts.define(replace(ability, text=prototype), ch)
    if native is None:
        return None
    if mode == "flesh":
        return {
            **native,
            "cond": {**native["cond"], "to": "creature_or_opponent"},
            "effects": [{"do": "damage", "who": "you", "n": {"event_amount": 1}}],
        }
    if mode == "justice":
        return {
            **native,
            "cond": {**native["cond"], "source_creature_or_spell": True},
            "effects": [{"do": "damage", "who": "event_player", "n": {"event_amount": 1}}],
        }
    if mode == "electryte":
        return {
            **native,
            "cond": {**native["cond"], "recipient_is_defender": True},
            "effects": [{"do": "damage_history_outcome", "mode": mode}],
        }
    return {
        **native,
        "effects": [
            {
                "do": "damage_history_outcome",
                "mode": mode,
                **(
                    {"who": "event_player"}
                    if mode in ("trumpet", "monsoon", "curse", "hunger", "growth")
                    else {}
                ),
            }
        ],
    }
