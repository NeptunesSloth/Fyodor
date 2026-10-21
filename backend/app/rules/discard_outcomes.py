"""Native recipes consuming explicit discard results and exact turn-history objects."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.rules.plan import Plan

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText
    from app.rules.scripts import Definition

Parsed = tuple[list[dict[str, Any]], Any, bool, str]


def native(text: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    return scripts.parse_effects(text)


def build(body: str) -> Parsed | None:
    text = re.sub(r"\s+", " ", body.strip())
    text = text[:1].upper() + text[1:]
    normalized = {
        "Target player discards two cards, then draws as many cards as they discarded this way.": "Target player discards two cards. Then that player draws a card for each card discarded this way.",
        "Target player draws a card, then discards a card. If that player discards an artifact card this way, untap ~.": "Target player draws a card, then discards a card. If an artifact card was discarded this way, untap ~.",
        "Each player may discard a card. Each player who discarded a card this way draws a card. If a creature card was discarded this way, you create a 1/2 white Moogle creature token with lifelink. Then if a noncreature card was discarded this way, put a +1/+1 counter on each Moogle you control.": "Each player discards up to one card. Each player who discarded a card this way draws a card. If a creature card was discarded this way, create a 1/2 white Moogle creature token with lifelink. Then if a noncreature card was discarded this way, put a +1/+1 counter on each Moogle you control.",
    }
    if text in normalized:
        got = native(normalized[text])
        return (*got, normalized[text]) if got else None
    if text == "Draw a card and reveal it. If it isn't a land card, discard it.":
        return [{"do": "original_draw_reveal"}], None, False, "Draw a card."
    simple = {
        "Draw cards equal to the number of cards target opponent discarded this turn.": (
            "history_count",
            "Target opponent discards a card.",
        ),
        "Return to your hand all cards in your graveyard that you cycled or discarded this turn.": (
            "history_return",
            "Draw a card.",
        ),
        "Draw a card. Then discard a card unless that land had a nonbasic land type.": (
            "returned_land",
            "Draw a card.",
        ),
        "You may discard your hand and draw cards equal to the damage dealt to target opponent this turn.": (
            "damage_draw",
            "Target opponent discards a card.",
        ),
    }
    if text in simple:
        mode, proto = simple[text]
        got = native(proto)
        assert got is not None
        return [{"do": "discard_outcome", "mode": mode}], got[1], False, proto
    if (
        text
        == "Draw three cards, then discard two cards at random. If two cards that share a card type are discarded this way, put two +1/+1 counters on ~."
    ):
        return (
            [
                {"do": "draw", "who": "you", "n": 3},
                {"do": "discard", "who": "you", "n": 2, "random": True, "as": "shared_discard"},
                {"do": "discard_outcome", "mode": "shared_type", "ref": "ref:shared_discard"},
            ],
            None,
            False,
            "Draw a card.",
        )
    if (
        text
        == "You and defending player each draw a card, then discard a card. Put two +1/+1 counters on ~ if you discarded the card with the greatest mana value among those cards or tied for greatest."
    ):
        return [{"do": "discard_outcome", "mode": "defender_start"}], None, False, "Draw a card."
    if (
        text
        == "Any number of target opponents each discard a card. For each of those opponents who didn't discard a card with mana value 4 or greater, draw a card."
    ):
        proto = "Any number of target opponents each discard a card."
        got = native(proto)
        if got is None:
            return None
        es = got[0]
        es[0]["as"] = "threshold_discard"
        return (
            [*es, {"do": "discard_outcome", "mode": "opponent_threshold", "ref": "ref:threshold_discard"}],
            got[1],
            False,
            proto,
        )
    if text == "That player discards a card at random. If the player does, they draw a card.":
        return (
            [
                {"do": "discard", "who": "event_player", "n": 1, "random": True, "as": "damage_discard"},
                {"do": "discard_outcome", "mode": "discard_then_draw", "ref": "ref:damage_discard"},
            ],
            None,
            False,
            "Draw a card.",
        )
    if (
        text
        == "Draw two cards. Then you may discard two cards. When you do, ~ deals X damage to each creature, where X is the greatest mana value among cards discarded this way."
    ):
        proto = "Draw two cards. You may discard two cards. When you do, ~ deals 1 damage to each creature."
        got = native(proto)
        assert got is not None
        return (
            [
                *got[0][:2],
                {
                    "do": "discard_outcome",
                    "mode": "reflexive_max_mv",
                    "ref": "ref:pay0",
                    "recipe": [got[0][-1]],
                },
            ],
            None,
            False,
            proto,
        )
    if (
        text
        == "You may discard a card. When you do, ~ deals X damage to any target, where X is the number of card types the discarded card has."
    ):
        proto = "You may discard a card. When you discard a card this way, ~ deals 1 damage to any target."
        got = native(proto)
        assert got is not None
        got[0][0]["as"] = "typed_discard"
        return (
            [
                got[0][0],
                {
                    "do": "discard_outcome",
                    "mode": "reflexive_types",
                    "ref": "ref:typed_discard",
                    "recipe": [got[0][1]],
                },
            ],
            None,
            got[2],
            proto,
        )
    if (
        text
        == "Sacrifice ~ unless you discard a card. When you discard a card this way, destroy target nonland permanent an opponent controls with mana value less than or equal to the mana value of the discarded card."
    ):
        got = native("Sacrifice ~ unless you discard a card.")
        assert got is not None
        return (
            [*got[0], {"do": "discard_outcome", "mode": "reflexive_destroy", "ref": "ref:pay0"}],
            None,
            False,
            "Draw a card.",
        )
    if (
        text
        == "Discard a card. If you do, draw a card. If a creature card was discarded this way, draw two cards instead."
        or text
        == "You may discard a card. If you do, draw a card. If a creature card was discarded this way, draw two cards instead."
    ):
        return (
            [
                {"do": "discard", "who": "you", "n": 1, "upto": True, "as": "creature_discard"},
                {"do": "discard_outcome", "mode": "creature_draw", "ref": "ref:creature_discard"},
            ],
            None,
            False,
            "Draw a card.",
        )
    if (
        text
        == "Discard a card at random. If you discard a creature card this way, return it from your graveyard to the battlefield unless any player pays 5 life."
    ):
        return (
            [
                {"do": "discard", "who": "you", "n": 1, "random": True, "as": "rift_discard"},
                {"do": "discard_outcome", "mode": "rift", "ref": "ref:rift_discard"},
            ],
            None,
            False,
            "Draw a card.",
        )
    return None


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    got = build(body)
    return got[:3] if got is not None else None


def definition(ability: AbilityText, ch: Characteristics) -> Definition | None:
    from dataclasses import replace

    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if ability.kind == "spell":
        lead, body = "", text
    elif ability.kind in ("activated", "loyalty") and ": " in text:
        prefix, body = text.split(": ", 1)
        lead = prefix + ": "
    elif ability.kind == "triggered" and ", " in text:
        prefix, body = text.split(", ", 1)
        lead = prefix + ", "
    else:
        return None
    got = build(body)
    if got is None:
        return None
    # Native target/cost/trigger construction remains authoritative.
    if body[:1].upper() + body[1:] == got[3]:
        return None
    base = scripts.define(replace(ability, text=lead + got[3]), ch)
    if base is None:
        return None
    base["effects"] = got[0]
    base["optional"] = got[2]
    return base


def insert(ctx: dict[str, Any], es: list[dict[str, Any]]) -> bool:
    i = ctx["next"]
    ctx["effects"][i:i] = es
    return True


def result_ids(plan: Plan, ctx: dict[str, Any], ref: str) -> list[str]:
    from app.rules import context, discarded_references

    key = ref.removeprefix("ref:")
    b = context.refs(ctx).get(key, {})
    current = key + ":result"
    context.refs(ctx)[current] = {"kind": "objects", "objects": b.get("moved") or b.get("objects") or []}
    return discarded_references.objects(plan, ctx, current)


def outcome(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects, history, selectors, this_way
    from app.rules.paid_sacrifice_effects import legacy

    mode = e["mode"]
    follow: list[dict[str, Any]] = []
    ids = result_ids(plan, ctx, e["ref"]) if e.get("ref") else []
    chars = [plan.ch(plan.state.cards[cid]) for cid in ids]
    if mode == "history_count":
        ps = effects._players(plan, ctx, "target")
        if ps:
            n = sum(
                f.amount for f in history.log_for(plan).facts if f.kind == "discard" and f.player == ps[0]
            )
            follow = [{"do": "draw", "who": "you", "n": n}]
    elif mode == "history_return":
        refs = []
        for f in history.log_for(plan).facts:
            if f.kind != "discard" or f.player != ctx["controller"]:
                continue
            if f.discarded_results is None:
                old = plan.state.cards.get((f.object_id or "").rsplit(".", 1)[0])
                if (
                    old is not None
                    and old.zone == ctx["controller"] + ":graveyard"
                    and plan.oid(old) == f.object_id
                ):
                    r = context.ref_of(plan, old.id)
                    if r is not None:
                        refs.append(r.model_dump(mode="json"))
                elif old is not None and old.zone == ctx["controller"] + ":graveyard":
                    return legacy(
                        plan,
                        ctx,
                        "This older save did not retain exact discard-result identities. Return the appropriate discarded cards by hand, then press Done.",
                    )
            else:
                refs.extend(r.model_dump(mode="json") for r in f.discarded_results)
        context.refs(ctx)["history_discards"] = {"kind": "objects", "objects": refs}
        from app.rules import discarded_references

        found = [
            c
            for c in discarded_references.objects(plan, ctx, "history_discards")
            if plan.state.cards[c].zone == ctx["controller"] + ":graveyard"
        ]
        context.bind_objects(plan, ctx, "history_return", found)
        follow = [{"do": "return_card", "who": "ref:history_return", "to": "hand"}]
    elif mode == "returned_land":
        from app.rules.layers import LAND_TYPES

        sid = ctx.get("stack_id")
        paid = plan.rules.payments.get(plan.oid(sid)) if sid else None
        if paid is None or paid.returned_objects is None:
            return legacy(
                plan,
                ctx,
                "This older save did not record the returned land’s battlefield identity. Apply the conditional discard by hand, then press Done.",
            )
        from app.rules.triggers import _snapshot_card

        snaps = [plan.rules.lki.get(oid) for oid in paid.returned_objects]
        qualifying = any(
            s is not None
            and set(_snapshot_card(plan, s)[1].subtypes).intersection(
                LAND_TYPES - set(selectors.BASIC_LAND_TYPES_SEL)
            )
            for s in snaps
        )
        follow = [
            {"do": "draw", "who": "you", "n": 1},
            *([{"do": "discard", "who": "you", "n": 1}] if not qualifying else []),
        ]
    elif mode == "damage_draw":
        ps = effects._players(plan, ctx, "target")
        n = sum(
            f.amount for f in history.log_for(plan).facts if f.kind == "damage" and ps and f.player == ps[0]
        )
        got = native(f"You may discard your hand. If you do, draw {n} cards.")
        assert got is not None
        follow = got[0]
    elif mode == "shared_type":
        if len(chars) == 2 and chars[0].types & chars[1].types:
            follow = [{"do": "add_counters", "who": "self", "kind": "+1/+1", "n": 2}]
    elif mode == "defender_start":
        people = list(dict.fromkeys([ctx["controller"], *effects._players(plan, ctx, "defending_player")]))
        context.bind_players(ctx, "cait_people", people)
        follow = [
            {"do": "draw", "who": "ref:cait_people", "n": 1},
            {"do": "discard", "who": "ref:cait_people", "n": 1, "as": "cait_discard"},
            {"do": "discard_outcome", "mode": "defender_compare", "ref": "ref:cait_discard"},
        ]
    elif mode == "defender_compare":
        ours = [
            plan.ch(plan.state.cards[c]).mana_value
            for c in ids
            if plan.state.cards[c].owner == ctx["controller"]
        ]
        greatest = max((ch.mana_value for ch in chars), default=0)
        if ours and max(ours) >= greatest:
            follow = [{"do": "add_counters", "who": "self", "kind": "+1/+1", "n": 2}]
    elif mode == "opponent_threshold":
        ps = effects._players(plan, ctx, "target")
        high = {plan.state.cards[c].owner for c in ids if plan.ch(plan.state.cards[c]).mana_value >= 4}
        follow = [{"do": "draw", "who": "you", "n": len(set(ps) - high)}]
    elif mode == "discard_then_draw":
        if this_way.count(
            plan, ctx, {"this_way": "discarded", "of": None, "ref_count": e["ref"].removeprefix("ref:")}
        ):
            follow = [{"do": "draw", "who": "event_player", "n": 1}]
    elif mode == "creature_draw":
        if ids:
            follow = [
                {"do": "draw", "who": "you", "n": 2 if any("Creature" in ch.types for ch in chars) else 1}
            ]
    elif mode == "rift":
        available = [
            c
            for c in ids
            if plan.state.cards[c].zone == ctx["controller"] + ":graveyard"
            and "Creature" in plan.ch(plan.state.cards[c]).types
        ]
        if available:
            context.bind_objects(plan, ctx, "rift_return", available)
            got = native(
                "Return target creature card from your graveyard to the battlefield unless any player pays 5 life."
            )
            assert got is not None
            follow = got[0]
            follow[-1]["who"] = "ref:rift_return"
    elif mode.startswith("reflexive_"):
        key = e["ref"].removeprefix("ref:")
        b = context.refs(ctx).get(key, {})
        ok = bool(b.get("ok")) if b.get("kind") == "payment" else bool(ids)
        if not ok:
            return True
        if mode == "reflexive_destroy":
            n = int(max((ch.mana_value for ch in chars), default=0))
            sel = selectors.Selector(
                controller="opponent", not_types=("Land",), compare=(("mv", "<=", n),)
            ).key()
            follow = [
                {
                    "do": "reflexive",
                    "cond": {"succeeded": key},
                    "ability": {
                        "kind": "triggered",
                        "trigger": "reflexive",
                        "effects": [{"do": "destroy", "who": "target"}],
                        "optional": False,
                        "target": {"what": sel},
                    },
                }
            ]
        else:
            from copy import deepcopy

            follow = deepcopy(e["recipe"])
            n = (
                int(max((ch.mana_value for ch in chars), default=0))
                if mode == "reflexive_max_mv"
                else len(set().union(*(ch.types for ch in chars)))
            )
            for item in follow:
                item["cond"] = (
                    {"succeeded": key}
                    if b.get("kind") == "payment"
                    else {
                        "value": {"this_way": "discarded", "of": None, "ref_count": key},
                        "op": ">=",
                        "n": 1,
                    }
                )
                item.pop("lki", None)
                for sub in item["ability"]["effects"]:
                    if sub.get("do") == "damage":
                        sub["n"] = n
    return insert(ctx, follow)


def original_draw(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import history

    before = list(history.log_for(plan).drawn.get(ctx["controller"], []))
    return insert(
        ctx, [{"do": "draw", "who": "you", "n": 1}, {"do": "original_draw_reveal_finish", "before": before}]
    )


def original_draw_finish(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, history

    log = history.log_for(plan)
    me = ctx["controller"]
    excluded = set(e["before"]) | set(log.drawn_replaced.get(me, [])) | set(log.drawn_counted.get(me, []))
    objects = [oid for oid in log.drawn.get(me, []) if oid not in excluded]
    ids = [
        oid.rsplit(".", 1)[0]
        for oid in objects
        if oid.rsplit(".", 1)[0] in plan.state.cards
        and plan.oid(oid.rsplit(".", 1)[0]) == oid
        and plan.state.cards[oid.rsplit(".", 1)[0]].zone == me + ":hand"
    ]
    if not ids:
        return True
    plan.do({"type": "reveal", "card_ids": ids}, actor=me)
    nonlands = [cid for cid in ids if "Land" not in plan.ch(plan.state.cards[cid]).types]
    context.bind_objects(plan, ctx, "drawn_nonlands", nonlands)
    return insert(ctx, [{"do": "discard_named", "who": "ref:drawn_nonlands"}])


PRIMITIVES = {
    "discard_outcome": outcome,
    "original_draw_reveal": original_draw,
    "original_draw_reveal_finish": original_draw_finish,
}
