"""Exact life instructions evaluated from public native history and real receipts.

Native life changes retain their original sources and queued continuations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.rules import context, selectors

if TYPE_CHECKING:
    from app.rules.plan import Plan

BODIES = {
    "Untap target creature you don't control and gain control of it. It gains haste until end of turn. At the beginning of the next end step, sacrifice it. If you do, you gain life equal to its toughness": (
        "spinal",
        "Untap target creature you don't control and gain control of it. It gains haste until end of turn.",
    ),
    "You draw X cards and you lose X life, where X is the mana value of a commander you own on the battlefield or in the command zone": (
        "study",
        "Draw a card.",
    ),
    "Target player loses life equal to the damage already dealt to that player this turn": (
        "punishment",
        "Target player loses 1 life.",
    ),
    "You gain X life, where X is twice the damage dealt to you so far this turn by artifacts": (
        "polarity",
        "You gain 1 life.",
    ),
    "Target opponent loses 1 life for each attacking creature you control. You gain that much life": (
        "shriek",
        "Target opponent loses 1 life.",
    ),
    "Choose target opponent. Create two 1/1 colorless Thopter artifact creature tokens with flying. Then the chosen player loses X life and you gain X life, where X is the number of artifacts you control": (
        "haunt",
        "Target opponent loses 1 life.",
    ),
    "You draw X cards and gain X life, where X is the number of colors among permanents you control and spells you've cast this turn": (
        "family",
        "Draw a card.",
    ),
    "Destroy all creatures. Each player loses life equal to the number of creatures they controlled that were destroyed this way": (
        "tempest",
        "Destroy all creatures.",
    ),
    "Destroy all artifacts. They can't be regenerated. The controller of each of those artifacts gains life equal to its mana value": (
        "seeds",
        "Destroy all artifacts. They can't be regenerated.",
    ),
}


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    item = BODIES.get(body.strip().rstrip("."))
    if not item:
        return None
    parsed = scripts.parse_effects(item[1])
    return ([{"do": "life_history_outcome", "mode": item[0]}], parsed[1], False) if parsed else None


def queued(ctx: dict[str, Any], steps: list[dict[str, Any]]) -> bool:
    ctx["effects"][ctx["next"] : ctx["next"]] = steps
    return True


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, history

    mode = e["mode"]
    log = history.log_for(plan)
    if mode == "blitz_loss":
        players = effects._players(plan, ctx, "target")
        if not players:
            return True
        n = log.lost.get(players[0], 0)
        return queued(
            ctx,
            [
                {"do": "lose_life", "who": "target", "n": n, "bind": "life_history_blitz_loss"},
                {"do": "life_history_finish", "mode": "blitz_loss"},
            ],
        )
    if mode == "blitz_random":
        import secrets

        from app.rules import randomness  # -- random choices (wave MBC-D) --
        keyword = randomness.choice(plan, plan.rng or secrets.SystemRandom(), ["flying", "indestructible"], kind="other", player=ctx["controller"])
        plan.note(str(ctx.get("name") or "It") + " randomly gains " + keyword)
        return queued(ctx, [{"do": "grant", "who": "self", "keywords": [keyword]}])
    if mode == "orgg_enter":
        n = max(0, plan.state.players[ctx["controller"]].life - 1)
        return queued(
            ctx,
            [
                {"do": "lose_life", "who": "you", "n": n, "bind": "life_history_orgg_loss"},
                {"do": "life_history_finish", "mode": "orgg_enter", "link": e["link"]},
            ],
        )
    if mode == "orgg_leave":
        key = str(ctx.get("source_object")) + ":" + str(e["link"])
        if (
            key not in plan.rules.entry_life_losses
            and ctx.get("source_object") not in plan.rules.entry_life_origins
        ):
            if key not in plan.rules.entry_life_notices:
                plan.note(
                    "Earlier entry life loss is unavailable for this source. Resolve this life-gain ability by hand."
                )
                plan.rules.entry_life_notices.append(key)
            return True
        return queued(ctx, [{"do": "gain_life", "who": "you", "n": plan.rules.entry_life_losses.get(key, 0)}])
    if mode == "scythe":
        return queued(
            ctx,
            [
                {"do": "discard", "who": "each_opponent", "n": 1, "as": "life_history_scythe"},
                {"do": "life_history_finish", "mode": mode},
            ],
        )
    if mode == "spinal":
        context.bind_objects(plan, ctx, "life_history_spinal", effects._cards(plan, ctx, "target"))
        return queued(
            ctx,
            [
                {"do": "gain_control", "who": "target", "untap": True},
                {"do": "grant", "who": "target", "keywords": ["haste"]},
                {"do": "delayed", "n": 1, "when": {"kind": "step", "step": "end", "whose": "next"}},
                {"do": "life_history_outcome", "mode": "spinal_sacrifice", "who": "ref:life_history_spinal"},
            ],
        )
    if mode == "spinal_sacrifice":
        from app.rules import values

        n = values.evaluate(plan, ctx, {"toughness": "ref:life_history_spinal"})
        return queued(
            ctx,
            [
                {"do": "sacrifice", "who": "ref:life_history_spinal", "as": "life_history_spinal_offered"},
                {"do": "life_history_finish", "mode": "spinal", "n": n},
            ],
        )
    if mode == "xathrid":
        from app.rules import prohibitions

        ids = [
            c.id
            for c in plan.state.cards.values()
            if c.zone.endswith(":battlefield")
            and c.controller == ctx["controller"]
            and "Creature" in plan.ch(c).types
            and plan.oid(c) != ctx.get("source_object")
            and not prohibitions.sacrifice_forbidden(plan, c)
        ]
        if effects._sacrifice_barred(plan, ctx, ctx["controller"]):
            ids = []
        context.bind_objects(plan, ctx, "life_history_offering", ids)
        return queued(
            ctx,
            [
                {
                    "do": "return_choice",
                    "who": "ref:life_history_offering",
                    "n": 1,
                    "to": "choose",
                    "as": "life_history_chosen",
                },
                {"do": "life_history_finish", "mode": "xathrid_chosen"},
            ],
        )
    if mode == "confidant":
        top = plan.state.zones.get(ctx["controller"] + ":library", [])[:1]
        context.bind_objects(plan, ctx, "life_history_surveilled", top)
        return queued(
            ctx, [{"do": "surveil", "who": "you", "n": 1}, {"do": "life_history_finish", "mode": mode}]
        )
    if mode == "racket":
        todo = e.get("players")
        if todo is None:
            todo = [p for p in plan.apnap() if p != ctx["controller"]]
        todo = [p for p in todo if p in plan.live()]
        if not todo:
            return True
        return queued(
            ctx,
            [
                {"do": "look_top", "n": 1, "player": "you", "reveal": True, "as": "life_history_racket"},
                {"do": "life_history_finish", "mode": "racket_reveal", "payer": todo[0], "rest": todo[1:]},
            ],
        )
    if mode == "warlock":
        from app.rules import scripts

        players = effects._players(plan, ctx, "target")
        if not players:
            return True
        body = (
            "Target opponent reveals their hand. You choose a nonland card from it. That player discards that card."
            if log.lost.get(players[0], 0) > 0
            else "Target opponent discards a card."
        )
        parsed = scripts.parse_effects(body)
        assert parsed is not None
        return queued(ctx, parsed[0])
    if mode == "study":
        return queued(
            ctx,
            [
                {
                    "do": "return_choice",
                    "sel": selectors.Selector(
                        commander=True, owner="you", zones=("battlefield", "command")
                    ).key(),
                    "n": 1,
                    "to": "choose",
                    "as": "life_history_commander",
                },
                {"do": "life_history_finish", "mode": mode},
            ],
        )
    if mode == "belbe":
        n = sum(amount > 0 for pid, amount in log.lost.items() if pid != ctx["controller"])
        return queued(ctx, [{"do": "add_mana", "who": "event_player", "sym": "C", "n": 2 * n}])
    if mode == "punishment":
        players = effects._players(plan, ctx, "target")
        return queued(
            ctx,
            [
                {
                    "do": "lose_life",
                    "who": "player:" + p,
                    "n": sum(f.amount for f in log.facts if f.kind == "damage" and f.player == p),
                }
                for p in players
            ],
        )
    if mode == "polarity":
        n = 2 * sum(
            f.amount
            for f in log.facts
            if f.kind == "damage" and f.player == ctx["controller"] and "Artifact" in f.source_types
        )
        return queued(ctx, [{"do": "gain_life", "who": "you", "n": n}])
    if mode == "shriek":
        n = sum(
            c.zone.endswith(":battlefield")
            and c.controller == ctx["controller"]
            and c.attacking is not None
            and "Creature" in plan.ch(c).types
            for c in plan.state.cards.values()
        )
        return queued(
            ctx,
            [
                {"do": "lose_life", "who": "target", "n": n, "bind": "life_history_lost"},
                {"do": "gain_life", "who": "you", "n": {"ref_amount": "life_history_lost"}},
            ],
        )
    if mode == "haunt":
        return queued(
            ctx,
            [
                {
                    "do": "create_token",
                    "who": "you",
                    "n": 2,
                    "token": {
                        "name": "Thopter",
                        "type_line": "Token Artifact Creature — Thopter",
                        "colors": [],
                        "power": "1",
                        "toughness": "1",
                        "text": "Flying",
                    },
                },
                {"do": "life_history_finish", "mode": mode},
            ],
        )
    if mode == "family":
        colors = set().union(
            *(
                set(plan.ch(c).colors)
                for c in plan.state.cards.values()
                if c.zone.endswith(":battlefield") and c.controller == ctx["controller"]
            ),
            *(set(c.colors) for c in log.casts if c.player == ctx["controller"]),
        )
        n = len(colors)
        return queued(ctx, [{"do": "draw", "who": "you", "n": n}, {"do": "gain_life", "who": "you", "n": n}])
    if mode == "tempest":
        return queued(
            ctx,
            [
                {
                    "do": "destroy",
                    "who": selectors.Selector(types=("Creature",)).key(),
                    "as": "life_history_destroyed",
                },
                {"do": "life_history_finish", "mode": mode},
            ],
        )
    if mode == "seeds":
        from app.rules import values

        totals = []
        for i, c in enumerate(list(plan.state.cards.values())):
            if c.zone.endswith(":battlefield") and "Artifact" in plan.ch(c).types:
                key = "life_history_artifact_" + str(i)
                context.bind_objects(plan, ctx, key, [c.id])
                totals.append(
                    {
                        "do": "gain_life",
                        "who": "player:" + c.controller,
                        "n": values.evaluate(plan, ctx, {"mana_value": "ref:" + key}),
                    }
                )
        return queued(
            ctx,
            [
                {
                    "do": "destroy",
                    "who": selectors.Selector(types=("Artifact",)).key(),
                },
                {"do": "no_regen"},
                *totals,
            ],
        )
    return True


def finish(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import this_way

    if e["mode"] == "blitz_loss":
        from app.rules import values

        return (
            queued(ctx, [{"do": "transform", "who": "self"}])
            if values.evaluate(plan, ctx, {"ref_amount": "life_history_blitz_loss"}) == 0
            else True
        )
    if e["mode"] == "orgg_enter":
        from app.rules import values

        key = str(ctx.get("source_object")) + ":" + str(e["link"])
        plan.rules.entry_life_losses[key] = plan.rules.entry_life_losses.get(key, 0) + values.evaluate(
            plan, ctx, {"ref_amount": "life_history_orgg_loss"}
        )
        return True
    if e["mode"] == "scythe":
        from app.game.rules_state import ObjectRef
        from app.rules import values

        rows = []
        for i, (new, old) in enumerate(
            this_way._matched(
                plan, ctx, {"this_way": "discarded", "of": None, "ref_count": "life_history_scythe"}
            )
        ):
            snap = context.snapshot(plan, ObjectRef.model_validate(old))
            c = plan.state.cards.get(old["card"])
            owner = snap.owner if snap else (c.owner if c else None)
            key = "life_history_scythe_" + str(i)
            context.refs(ctx)[key] = {"kind": "objects", "objects": [new], "was": [old]}
            if owner:
                rows.append((owner, values.evaluate(plan, ctx, {"mana_value": "ref:" + key})))
        high = max((n for _, n in rows), default=0)
        return queued(ctx, [{"do": "lose_life", "who": "player:" + p, "n": n} for p, n in rows if n == high])
    if e["mode"] == "spinal":
        if this_way.count(
            plan, ctx, {"this_way": "sacrificed", "of": None, "ref_count": "life_history_spinal_offered"}
        ):
            return queued(ctx, [{"do": "gain_life", "who": "you", "n": e["n"]}])
        return True
    if e["mode"] == "xathrid_chosen":
        from app.rules import values

        n = values.evaluate(plan, ctx, {"power": "ref:life_history_chosen"})
        return queued(
            ctx,
            [
                {"do": "sacrifice", "who": "ref:life_history_chosen", "as": "life_history_offered"},
                {"do": "life_history_finish", "mode": "xathrid_result", "n": n},
            ],
        )
    if e["mode"] == "xathrid_result":
        if this_way.count(
            plan, ctx, {"this_way": "sacrificed", "of": None, "ref_count": "life_history_offered"}
        ):
            return queued(ctx, [{"do": "lose_life", "who": "each_opponent", "n": e["n"]}])
        return queued(ctx, [{"do": "tap", "who": "self"}, {"do": "lose_life", "who": "you", "n": 7}])
    if e["mode"] == "confidant":
        from app.rules import history, values

        context.bind_moved(
            plan,
            ctx,
            "life_history_surveilled",
            context._object_refs(ctx, "life_history_surveilled", was=True),
        )
        ids = context.objects(plan, ctx, "life_history_surveilled")
        if not ids or plan.state.cards[ids[0]].zone != ctx["controller"] + ":graveyard":
            return True
        if values.evaluate(plan, ctx, {"mana_value": "ref:life_history_surveilled"}) > history.log_for(
            plan
        ).gained.get(ctx["controller"], 0):
            return True
        return queued(ctx, [{"do": "return_card", "who": "ref:life_history_surveilled", "to": "hand"}])
    if e["mode"] == "racket_reveal":
        from app.rules import values

        steps = []
        if context.objects(plan, ctx, "life_history_racket"):
            n = values.evaluate(plan, ctx, {"mana_value": "ref:life_history_racket"})
            steps = [
                {
                    "do": "optional_payment",
                    "who": "player:" + e["payer"],
                    "cost": "Pay " + str(n) + " life",
                    "bind": "life_history_racket_paid",
                },
                {"do": "only_if", "cond": {"succeeded": "life_history_racket_paid"}, "skip": 1},
                {"do": "exile", "who": "ref:life_history_racket"},
                {"do": "only_if", "cond": {"not": {"succeeded": "life_history_racket_paid"}}, "skip": 1},
                {"do": "return_card", "who": "ref:life_history_racket", "to": "hand"},
            ]
        return queued(ctx, [*steps, {"do": "life_history_outcome", "mode": "racket", "players": e["rest"]}])
    if e["mode"] == "study":
        from app.rules import values

        n = values.evaluate(plan, ctx, {"mana_value": "ref:life_history_commander"})
        return queued(ctx, [{"do": "draw", "who": "you", "n": n}, {"do": "lose_life", "who": "you", "n": n}])
    if e["mode"] == "haunt":
        n = sum(
            c.zone.endswith(":battlefield")
            and c.controller == ctx["controller"]
            and "Artifact" in plan.ch(c).types
            for c in plan.state.cards.values()
        )
        return queued(
            ctx, [{"do": "lose_life", "who": "target", "n": n}, {"do": "gain_life", "who": "you", "n": n}]
        )
    if e["mode"] == "tempest":
        counts = this_way.by_controller(
            plan, ctx, {"this_way": "destroyed", "of": None, "ref_count": "life_history_destroyed"}
        )
        return queued(ctx, [{"do": "lose_life", "who": "player:" + p, "n": n} for p, n in counts.items()])
    return True


PRIMITIVES = {"life_history_outcome": run, "life_history_finish": finish}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if ability.kind == "triggered":
        if (
            text
            == "At the beginning of your end step, target opponent loses life equal to the life that player lost this turn. If no life is lost this way, transform ~."
        ):
            native = scripts.define(
                replace(ability, text="At the beginning of your end step, target opponent loses 1 life."), ch
            )
            return (
                {**native, "effects": [{"do": "life_history_outcome", "mode": "blitz_loss"}]}
                if native
                else None
            )
        if (
            text
            == "At the beginning of combat on your turn, choose flying or indestructible at random. ~ gains that ability until end of turn."
        ):
            native = scripts.define(
                replace(
                    ability, text="At the beginning of combat on your turn, ~ gains flying until end of turn."
                ),
                ch,
            )
            return (
                {**native, "effects": [{"do": "life_history_outcome", "mode": "blitz_random"}]}
                if native
                else None
            )
        if text in (
            "When ~ enters, you lose all but 1 life.",
            "When ~ leaves the battlefield, you gain life equal to the life you lost when it entered.",
        ):
            entries = [
                a.index
                for a in ch.abilities
                if scripts.self_text(a.text, ch.name) == "When ~ enters, you lose all but 1 life."
            ]
            link = (
                ability.index
                if text.startswith("When ~ enters")
                else max((i for i in entries if i < ability.index), default=-1)
            )
            prototype = (
                "When ~ enters, you lose 1 life."
                if text.startswith("When ~ enters")
                else "When ~ leaves the battlefield, you gain 1 life."
            )
            native = scripts.define(replace(ability, text=prototype), ch)
            return (
                {
                    **native,
                    "effects": [
                        {
                            "do": "life_history_outcome",
                            "mode": "orgg_enter" if text.startswith("When ~ enters") else "orgg_leave",
                            "link": link,
                        }
                    ],
                }
                if native
                else None
            )
        if (
            text
            == "Whenever ~ deals combat damage to a player, each opponent discards a card. Each player who discarded a card with the greatest mana value among cards discarded this way loses life equal to that mana value."
        ):
            native = scripts.define(
                replace(
                    ability, text="Whenever ~ deals combat damage to a player, each opponent discards a card."
                ),
                ch,
            )
            return (
                {**native, "effects": [{"do": "life_history_outcome", "mode": "scythe"}]} if native else None
            )
        if (
            text
            == "At the beginning of your upkeep, sacrifice a creature other than ~, then each opponent loses life equal to the sacrificed creature's power. If you can't sacrifice a creature, tap ~ and you lose 7 life."
        ):
            native = scripts.define(
                replace(ability, text="At the beginning of your upkeep, you gain 1 life."), ch
            )
            return (
                {**native, "effects": [{"do": "life_history_outcome", "mode": "xathrid"}]} if native else None
            )
        if (
            text
            == "At the beginning of your end step, if you gained life this turn, surveil 1. If you put a card with mana value less than or equal to the amount of life you gained this turn into your graveyard this way, put that card into your hand."
        ):
            native = scripts.define(
                replace(
                    ability,
                    text="At the beginning of your end step, if you gained life this turn, surveil 1.",
                ),
                ch,
            )
            return (
                {**native, "effects": [{"do": "life_history_outcome", "mode": "confidant"}]}
                if native
                else None
            )
        if (
            text
            == "At the beginning of your upkeep, repeat the following process for each opponent in turn order. Reveal the top card of your library. That player may pay life equal to that card's mana value. If they do, exile that card. Otherwise, put it into your hand."
        ):
            native = scripts.define(
                replace(ability, text="At the beginning of your upkeep, you gain 1 life."), ch
            )
            return (
                {**native, "effects": [{"do": "life_history_outcome", "mode": "racket"}]} if native else None
            )
        if (
            text
            == "When ~ enters, choose target opponent. If they lost life this turn, they reveal their hand, you choose a nonland card from it, and they discard that card. Otherwise, they discard a card."
        ):
            native = scripts.define(
                replace(ability, text="When ~ enters, target opponent discards a card."), ch
            )
            return (
                {**native, "effects": [{"do": "life_history_outcome", "mode": "warlock"}]} if native else None
            )
        if (
            text
            == "Whenever you gain life, you may pay {1}{W}. If you do, put a +1/+1 counter on target creature for each 1 life you gained."
        ):
            return scripts.define(
                replace(
                    ability,
                    text="Whenever you gain life, you may pay {1}{W}. If you do, put that many +1/+1 counters on target creature.",
                ),
                ch,
            )
        if (
            text
            == "At the beginning of each postcombat main phase, the active player adds {C}{C} for each of your opponents who lost life this turn."
        ):
            native = scripts.define(
                replace(ability, text="At the beginning of each postcombat main phase, you gain 1 life."), ch
            )
            return (
                {
                    **native,
                    "effects": [{"do": "life_history_outcome", "mode": "belbe", "who": "event_player"}],
                }
                if native
                else None
            )
        return None
    if ability.kind != "spell":
        return None
    body = scripts.self_text(ability.text, ch.name).strip().rstrip(".")
    item = BODIES.get(body)
    if item is None:
        return None
    parsed = parse(body)
    native = scripts.define(replace(ability, text=item[1]), ch)
    return {**native, "effects": parsed[0]} if native and parsed else None
