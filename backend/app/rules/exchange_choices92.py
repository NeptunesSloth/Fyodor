"""Original-object and player-owned choices for exact permanent exchanges."""

from __future__ import annotations

import base64
import json
from dataclasses import replace
from typing import Any

CONFUSION = "Whenever an artifact, creature, or enchantment enters, its controller chooses target permanent another player controls that shares a card type with it. Exchange control of those permanents."
CULTURAL = "Choose any number of creatures target player controls. Choose the same number of creatures another target player controls. Those players exchange control of those creatures."
JUXTAPOSE = "You and target player exchange control of the creature you each control with the greatest mana value. Then exchange control of artifacts the same way. If two or more permanents a player controls are tied for greatest, their controller chooses one of them."
MARK = "exchange_choices92:"


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    text = scripts.self_text(ability.text, ch.name)
    if text == CONFUSION:
        native = scripts.define(
            replace(ability, text="Whenever an artifact, creature, or enchantment enters, draw a card."), ch
        )
        if native:
            return {
                **native,
                "target": {"what": selectors.Selector(extras=(MARK,)).key()},
                "target_choice": "event_player",
                "exchange_choice92": True,
                "effects": [{"do": "exchange_control", "who": "ref:event", "with": "target"}],
            }
    if text == CULTURAL:
        return {
            "kind": "spell",
            "target": None,
            "targets": [
                {"what": "player", "min": 1, "max": 1},
                {"what": "player", "min": 1, "max": 1, "distinct_from": [0]},
            ],
            "effects": [{"do": "exchange_cultural92"}],
        }
    if text == JUXTAPOSE:
        return {
            "kind": "spell",
            "target": {"what": "player"},
            "effects": [
                {"do": "exchange_juxtapose92", "type": "Creature"},
                {"do": "exchange_juxtapose92", "type": "Artifact"},
            ],
        }
    return None


def bind(plan: Any, pending: Any) -> None:
    from app.rules import selectors

    if not pending.ability.get("exchange_choice92") or pending.event is None:
        return
    if len(pending.event.objects) != 1 or len(pending.event.players) != 1:
        return
    obj = pending.event.objects[0]
    data = {"card": obj.card, "oid": obj.object_id, "player": pending.event.players[0]}
    marker = MARK + base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
    pending.ability["target"] = {"what": selectors.Selector(extras=(marker,)).key()}


def matches(plan: Any, card: Any, ch: Any, marker: str) -> bool:
    from app.rules.triggers import _snapshot_card

    if marker == MARK:
        return False
    data = json.loads(base64.urlsafe_b64decode(marker[len(MARK) :]).decode())
    if card.controller == data["player"]:
        return False
    source = plan.state.cards.get(data["card"])
    if (
        source is not None
        and plan.in_game(source)
        and source.zone.endswith(":battlefield")
        and plan.oid(source) == data["oid"]
    ):
        types = plan.ch(source).types
    elif (snapshot := plan.rules.lki.get(data["oid"])) is not None:
        _, old = _snapshot_card(plan, snapshot)
        types = old.types
    else:
        return False
    return bool(ch.types & types)


def cultural(plan: Any, ctx: Any, effect: Any) -> bool:
    from app.rules import context, effects, selectors

    groups = ctx.get("groups") or []
    if len(groups) != 2 or not all(len(g) == 1 and g[0] for g in groups):
        return True
    players = [g[0]["id"] for g in groups]
    if len(set(players)) != 2 or not set(players) <= set(plan.live()):
        return True
    sel = selectors.Selector(types=("Creature",)).key()
    cap = min(len(effects._controlled(plan, sel, p, ctx.get("source_card"))) for p in players)
    for key, player in zip(("cultural_first92", "cultural_second92"), players, strict=True):
        context.bind_players(ctx, key, [player])
    ctx["effects"][ctx["next"] : ctx["next"]] = [
        {
            "do": "player_chooses",
            "who": "ref:cultural_first92",
            "by": "you",
            "sel": sel,
            "n": cap,
            "upto": True,
            "optional": True,
            "as": "cultural_a92",
            "label": "creatures",
        },
        {"do": "exchange_second_cohort92", "players": players},
    ]
    return True


def second_cohort(plan: Any, ctx: Any, effect: Any) -> bool:
    from app.rules import context, selectors

    count = len(context.refs(ctx).get("cultural_a92", {}).get("objects") or [])
    ctx["effects"][ctx["next"] : ctx["next"]] = [
        {
            "do": "player_chooses",
            "who": "ref:cultural_second92",
            "by": "you",
            "sel": selectors.Selector(types=("Creature",)).key(),
            "n": count,
            "as": "cultural_b92",
            "label": "creatures",
        },
        {"do": "exchange_cohorts92", "players": effect["players"], "count": count},
    ]
    return True


def cohorts(plan: Any, ctx: Any, effect: Any) -> bool:
    from app.rules import context, effects, layers

    players = effect["players"]
    first, second = [context.objects(plan, ctx, key) for key in ("cultural_a92", "cultural_b92")]
    if (
        not first
        or len(first) != effect["count"]
        or len(second) != effect["count"]
        or not set(players) <= set(plan.live())
    ):
        return True
    if any(
        plan.state.cards[c].controller != p or not plan.in_game(plan.state.cards[c])
        for ids, p in zip((first, second), players, strict=True)
        for c in ids
    ):
        return True
    effects._control_effect(plan, ctx, first, players[1], "permanent")
    effects._control_effect(plan, ctx, second, players[0], "permanent")
    layers.control_sync(plan)
    return True


def juxtapose(plan: Any, ctx: Any, effect: Any) -> bool:
    from app.rules import context, selectors

    targets = [r["id"] for r in ctx.get("targets", []) if r["id"] in plan.live()]
    if len(targets) != 1 or targets[0] == ctx["controller"]:
        return True
    kind = effect["type"]
    binding = "juxtapose_" + kind.lower() + "92"
    context.bind_players(ctx, binding + "_players", [ctx["controller"], targets[0]])
    sel = selectors.Selector(types=(kind,), extras=(f"greatest_own:mana_value:{kind}",)).key()
    ctx["effects"][ctx["next"] : ctx["next"]] = [
        {
            "do": "player_chooses",
            "who": "ref:" + binding + "_players",
            "sel": sel,
            "n": 1,
            "as": binding,
            "label": kind.lower(),
        },
        {"do": "exchange_control", "who": "ref:" + binding},
    ]
    return True


PRIMITIVES = {
    "exchange_cultural92": cultural,
    "exchange_cohorts92": cohorts,
    "exchange_second_cohort92": second_cohort,
    "exchange_juxtapose92": juxtapose,
}
