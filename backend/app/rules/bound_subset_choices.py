"""Exact resolution-time subsets retain their complement before native effects move them."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = "bound_subset"
POOL = "subset_pool"
SELECTED = "subset_selected"
OTHER = "subset_other"
CHOOSER = "subset_chooser"


def _step(mode: str, **flags: Any) -> dict[str, Any]:
    return {"do": STEP, "mode": mode, **flags}


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts
    from app.rules.nontarget_creature_choices import choose, key

    text = body.strip()
    text = text[:1].upper() + text[1:]
    pairs = {
        "Choose two target creatures controlled by the same opponent. That player chooses one of those creatures. ~ deals 5 damage to that creature, and the other can't block this turn.": "agony",
        "Choose two target creatures controlled by the same player. That player sacrifices one of them of their choice.": "incriminate",
        "Choose two target creatures controlled by the same player. Exile one of those creatures and put two +1/+1 counters on the other.": "cannibalize",
        "Choose two target creatures controlled by the same player. Their controller chooses and sacrifices one of them. Return the other to its owner's hand.": "spite",
        "Choose two target creatures controlled by the same opponent. That player chooses and sacrifices one of those creatures. Put a -1/-1 counter on the other.": "retribution",
    }
    if text in pairs:
        what = key("creature an opponent controls" if "same opponent" in text else "creature")
        return (
            [_step("prepare", action=pairs[text], who="target:0"), _step("partition", action=pairs[text])],
            [{"what": what, "min": 2, "max": 2, "same_controller": True}],
            False,
        )
    if (
        text
        == "Choose up to two target creature cards in your graveyard. An opponent chooses one of them. Return that card to your hand. Return the other to the battlefield under your control. It gains haste. Exile it at the beginning of the next end step."
    ):
        prototype = scripts.parse_effects(
            "Return up to two target creature cards from your graveyard to your hand."
        )
        assert prototype is not None
        return (
            [_step("prepare", action="wake", who="target:0"), _step("partition", action="wake")],
            prototype[1],
            False,
        )
    if (
        text
        == "An opponent chooses one of the exiled cards. You put that card on the bottom of your library and return the other to the battlefield tapped. You become the monarch."
    ):
        return (
            [_step("prepare", action="coin", who="cost:exiled"), _step("partition", action="coin")],
            None,
            False,
        )
    if (
        text
        == "Choose a nonland permanent you don't control, then each other player chooses a nonland permanent they don't control that hasn't been chosen this way. Destroy all other nonland permanents."
    ):
        return (
            [
                choose(
                    "nonland permanent you don't control",
                    who="each_player",
                    start="you",
                    any=True,
                    any_by_chooser=True,
                    distinct=True,
                    rest="destroy",
                    rest_sel=key("nonland permanent"),
                )
            ],
            None,
            False,
        )
    if text == "Target player chooses a card in their hand and discards the rest.":
        return (
            [_step("prepare", action="monomania"), _step("partition", action="monomania")],
            "player",
            False,
        )
    if (
        text
        == "Target opponent chooses a creature they control. Other creatures they control can't block this turn."
    ):
        return ([_step("prepare", action="warcry"), _step("partition", action="warcry")], "opponent", False)
    if (
        text
        == "Target opponent chooses a permanent they control and returns it to its owner's hand. Then they shuffle each nonland permanent they control into its owner's library."
    ):
        return (
            [_step("prepare", action="pilgrim"), _step("partition", action="pilgrim"), _step("pilgrim_rest")],
            "opponent",
            False,
        )
    return None


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if (
        ability.kind == "activated"
        and text
        == "{3}{W}, {T}, Exile two creature cards from your graveyard, Sacrifice ~: An opponent chooses one of the exiled cards. You put that card on the bottom of your library and return the other to the battlefield tapped. You become the monarch."
    ):
        cost = scripts.parse_ability_cost(ability.cost, card_name=ch.name)
        if (
            not cost.unsupported
            and [part.kind for part in cost.components]
            == ["MANA", "TAP", "EXILE_FROM_GRAVEYARD", "SACRIFICE"]
            and cost.components[2].amount == 2
        ):
            return {
                "kind": "activated",
                "cost": ability.cost,
                "effects": [
                    _step("prepare", action="coin", who="cost:exiled"),
                    _step("partition", action="coin"),
                ],
            }
        return None
    if ability.kind != "triggered":
        return None
    if (
        text
        == "Whenever ~ attacks, defending player chooses a nonland card in your graveyard. Return that card to your hand. ~ gets +X/+0 until end of turn, where X is the mana value of that card."
    ):
        prototype = scripts.define(replace(ability, text="Whenever ~ attacks, you gain 1 life."), ch)
        if prototype is not None:
            return {
                **prototype,
                "effects": [_step("prepare", action="kami"), _step("partition", action="kami")],
            }
    if (
        text
        == "Whenever ~ deals combat damage to a player, you may have that player return target permanent card from their graveyard to their hand. If you do, that player chooses a permanent card in your graveyard, then you put it onto the battlefield under your control."
    ):
        prototype = scripts.define(
            replace(
                ability,
                text="Whenever ~ deals combat damage to a player, return target permanent card from that player's graveyard to their hand.",
            ),
            ch,
        )
        if prototype is not None:
            return {
                **prototype,
                "optional": True,
                "effects": [
                    *prototype["effects"],
                    _step("prepare", action="neyam"),
                    _step("partition", action="neyam"),
                ],
            }
    return None


def _insert(ctx: dict[str, Any], steps: list[dict[str, Any]]) -> None:
    at = int(ctx.get("next") or 0)
    ctx["effects"][at:at] = steps


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects, grouped_discard, prohibitions, selectors
    from app.rules.nontarget_creature_choices import key

    mode = e["mode"]
    action = e.get("action")
    if mode == "pilgrim_rest":
        remaining_players = context.players(plan, ctx, CHOOSER)
        cards = [
            cid
            for cid, c in plan.state.cards.items()
            if remaining_players
            and c.controller == remaining_players[0]
            and c.zone.endswith(":battlefield")
            and not plan.ch(c).is_land
        ]
        context.bind_objects(plan, ctx, OTHER, cards)
        _insert(ctx, [{"do": "to_library", "who": "ref:" + OTHER, "place": "shuffle"}])
        return True
    if mode == "prepare":
        pool: list[str] = []
        players: list[str] = []
        steps: list[dict[str, Any]] = []
        if action in ("agony", "incriminate", "spite", "retribution", "wake", "coin", "cannibalize"):
            pool = effects._cards(plan, ctx, e["who"])
            if action in ("wake", "coin"):
                steps.append({"do": "choose_opponent", "as": CHOOSER})
            elif pool:
                players = [ctx["controller"] if action == "cannibalize" else plan.state.cards[pool[0]].controller]  # (wave 110J) Cannibalize: its caster picks
        else:
            players = effects._players(
                plan,
                ctx,
                "defending_player" if action == "kami" else "event_player" if action == "neyam" else "target",
            )
            if action in ("kami", "neyam"):
                pool = selectors.candidates(
                    plan,
                    selectors.from_key(
                        key(
                            "nonland card in your graveyard"
                            if action == "kami"
                            else "permanent card in your graveyard"
                        )
                    ),
                    ctx["controller"],
                    ctx.get("source_card"),
                )
            elif players:
                pid = players[0]
                pool = (
                    list(plan.state.zones.get(f"{pid}:hand", []))
                    if action == "monomania"
                    else [
                        cid
                        for cid, c in plan.state.cards.items()
                        if c.controller == pid
                        and c.zone.endswith(":battlefield")
                        and (action != "warcry" or plan.ch(c).is_creature)
                    ]
                )
        context.bind_objects(plan, ctx, POOL, pool)
        if players:
            context.bind_players(ctx, CHOOSER, players)
        selectable = pool
        if action in ("incriminate", "spite", "retribution"):
            selectable = [
                cid
                for cid in pool
                if not prohibitions.sacrifice_forbidden(plan, plan.state.cards[cid])
                and not prohibitions.cant_cause_sacrifice(
                    plan, plan.state.cards[cid].controller, ctx["controller"]
                )
            ]
        context.bind_objects(plan, ctx, "subset_selectable", selectable)
        steps.append(
            {
                "do": "return_choice",
                "who": "ref:subset_selectable",
                "to": "choose",
                "n": 1,
                "chooser": "ref:" + CHOOSER,
                "as": SELECTED,
            }
        )
        _insert(ctx, steps)
        return True
    if mode == "partition":
        selected = context.objects(plan, ctx, SELECTED)
        pool = context.objects(plan, ctx, POOL)
        other = [cid for cid in pool if cid not in selected] if len(selected) == 1 else []
        context.bind_objects(plan, ctx, OTHER, other)
        first = "ref:" + SELECTED
        rest = "ref:" + OTHER
        tail: list[dict[str, Any]] = []
        if action == "agony":
            tail = [
                {"do": "damage", "who": first, "n": 5},
                {"do": "restrict", "who": rest, "rules": ["cant_block"]},
            ]
        elif action in ("incriminate", "spite", "retribution"):
            tail = [{"do": "sacrifice", "who": first, "by": "controller"}]
            if action == "spite":
                tail.append({"do": "bounce", "who": rest})
            elif action == "retribution":
                tail.append({"do": "add_counters", "who": rest, "kind": "-1/-1", "n": 1})
        elif action == "cannibalize":  # (wave 110J) 608.2c: the caster picks the one to exile; the other keeps the counters
            tail = [{"do": "exile", "who": first}, {"do": "add_counters", "who": rest, "kind": "+1/+1", "n": 2}]
        elif action == "coin":
            tail = [
                {"do": "to_library", "who": first, "place": "bottom"},
                {"do": "return_card", "who": rest, "to": "battlefield", "tapped": True, "under": "you"},
                {"do": "monarch", "who": "you"},
            ]
        elif action == "wake":
            tail = [
                {"do": "return_card", "who": first, "to": "hand", "under": "owner"},
                {
                    "do": "return_card",
                    "who": rest,
                    "to": "battlefield",
                    "under": "you",
                    "as": "subset_arrival",
                },
                {
                    "do": "grant",
                    "who": "ref:subset_arrival",
                    "keywords": ["haste"],
                    "duration": "permanent",
                    "as": "subset_hasty",
                },
                {"do": "delayed", "when": {"kind": "step", "step": "end", "whose": "next"}, "n": 1},
                {"do": "deferred:exile", "who": "ref:subset_hasty"},
            ]
        elif action == "kami":
            n = int(plan.ch(plan.state.cards[selected[0]]).mana_value) if selected else 0
            tail = [
                {"do": "return_card", "who": first, "to": "hand", "under": "owner"},
                {"do": "pump", "who": "self", "p": n, "t": 0},
            ]
        elif action == "neyam":
            tail = [{"do": "return_card", "who": first, "to": "battlefield", "under": "you"}]
        elif action == "monomania":
            return grouped_discard.begin_cards(plan, ctx, other)
        elif action == "warcry":
            tail = [{"do": "restrict", "who": rest, "rules": ["cant_block"]}]
        elif action == "pilgrim":
            tail = [{"do": "bounce", "who": first}]
        _insert(ctx, tail)
        return True
    raise ValueError(mode)


PRIMITIVES = {STEP: run}
