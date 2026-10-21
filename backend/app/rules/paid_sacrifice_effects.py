"""Native effect recipes sized by immutable direct paid sacrifices."""

from __future__ import annotations

import copy
import re
from typing import TYPE_CHECKING, Any

from app.rules.plan import Plan

if TYPE_CHECKING:
    from app.game.rules_state import Decision
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText
    from app.rules.scripts import Definition

# Each recipe uses existing primitives; only the computed scalar comes from the cost LKI.
PROTOTYPES = {
    "discard_power": "Target player discards X cards.",
    "damage_total_power": "~ deals X damage to any target.",
    "damage_half_power": "~ deals X damage to any target.",
    "damage_red_symbols": "~ deals X damage to any target.",
    "suspected_draw": "Draw a card.",
    "look_power": "Reveal the top X cards of your library. Put one of them into your hand and exile the rest.",
}

PATTERNS = {
    "Draw a card. If the sacrificed creature was suspected, draw two cards instead.": "suspected_draw",
    "Target player discards a number of cards equal to the sacrificed creature's power.": "discard_power",
    "~ deals damage to any target equal to the total power of the sacrificed creatures.": "damage_total_power",
    "~ deals damage to any target equal to half the sacrificed creature's power, rounded down.": "damage_half_power",
    "~ deals damage to any target equal to the number of red mana symbols in the sacrificed creature's mana cost.": "damage_red_symbols",
    "Reveal a number of cards from the top of your library equal to the sacrificed creature's power. Put one into your hand and exile the rest.": "look_power",
    "Destroy each creature with the same mana value as the sacrificed creature.": "destroy_same_mv",
    "Destroy all creatures that share a creature type with the sacrificed creature. They can't be regenerated.": "destroy_shared_creature_type",
    "Target player reveals their hand and discards all cards of each of the sacrificed creature's colors.": "discard_shared_color",
    "If there were three or more card types among the sacrificed permanents, each opponent loses 3 life, you gain 3 life, and you draw three cards.": "three_paid_types",
}


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    text = re.sub(r"\s+", " ", body.strip())
    text = text.replace("1 plus that creature's mana value", "1 plus the sacrificed creature's mana value")
    if (
        text
        == "Search your library for an Equipment or Vehicle card, put that card onto the battlefield, then shuffle. If it has mana value less than the sacrificed permanent's mana value, scry 2."
    ):
        native = scripts.parse_effects(
            "Search your library for an Equipment or Vehicle card, put it onto the battlefield, then shuffle."
        )
        if native is None:
            return None
        es, target, may = native
        es[0]["as"] = "anchor_found"
        return (
            [
                *es,
                {
                    "do": "paid_sacrifice_effect",
                    "mode": "anchor_compare",
                    "cost_source": "cost:sacrificed",
                    "as": "paid_sacrifices",
                    "found_ref": "ref:anchor_found",
                },
            ],
            target,
            may,
        )
    if (
        text
        == "Search your library for a creature card that shares a creature type with the sacrificed creature and has mana value equal to 1 plus the sacrificed creature's mana value. Put that card onto the battlefield, then shuffle."
    ):
        return (
            [
                {
                    "do": "paid_sacrifice_effect",
                    "mode": "pyre",
                    "cost_source": "cost:sacrificed",
                    "as": "paid_sacrifices",
                }
            ],
            None,
            False,
        )
    if (
        text
        == "Return target creature card from your graveyard to the battlefield if its power is less than or equal to the sacrificed creature's power."
    ):
        native = scripts.parse_effects("Return target creature card from your graveyard to the battlefield.")
        assert native is not None
        return (
            [
                {
                    "do": "paid_sacrifice_effect",
                    "mode": "conditional_return",
                    "cost_source": "cost:sacrificed",
                    "as": "paid_sacrifices",
                }
            ],
            native[1],
            False,
        )
    mode = PATTERNS.get(text)
    if mode is None:
        return None
    prototype = PROTOTYPES.get(mode)
    native = scripts.parse_effects(prototype) if prototype else None
    # Derive the target group from a native effect prototype.
    target = native[1] if native else "player" if mode == "discard_shared_color" else None
    recipe = native[0] if native else []
    return (
        [
            {
                "do": "paid_sacrifice_effect",
                "cost_source": "cost:sacrificed",
                "mode": mode,
                "recipe": recipe,
                "as": "paid_sacrifices",
            }
        ],
        target,
        False,
    )


def lki(
    plan: Plan, ctx: dict[str, Any], binding_name: str = "paid_sacrifices"
) -> list[tuple[CardInstance, Characteristics]]:
    from app.rules import context, this_way

    binding = this_way.cost_objects(plan, ctx, this_way.COST, "sacrificed")
    ctx.setdefault("refs", {})[binding_name] = {"kind": "objects", **binding}
    # context.infos recovers original OID snapshots, including removed tokens.
    return list(context.infos(plan, ctx, binding_name))


def replace_x(value: Any, n: int) -> Any:
    if value == {"x": 1}:
        return max(0, n)
    if isinstance(value, dict):
        return {k: replace_x(v, n) for k, v in value.items()}
    if isinstance(value, list):
        return [replace_x(v, n) for v in value]
    return copy.deepcopy(value)


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    sid = ctx.get("stack_id")
    if sid is None or plan.rules.payments.get(plan.oid(sid)) is None:
        return legacy(
            plan,
            ctx,
            "This older save has no direct sacrifice receipt. Apply this payment-dependent instruction by hand, then press Done.",
        )
    infos = lki(plan, ctx, e.get("as", "paid_sacrifices"))
    mode = e["mode"]
    # Paid characteristics come solely from the original snapshots,
    # not from physical cards that may have re-entered as different objects.
    if mode in ("discard_power", "look_power"):
        n = power(infos[0][1]) if len(infos) == 1 else 0
    elif mode == "damage_total_power":
        n = sum(power(ch) for _, ch in infos)
    elif mode == "damage_half_power":
        n = power(infos[0][1]) // 2 if len(infos) == 1 else 0
    elif mode == "damage_red_symbols":
        # Each mana symbol containing R counts once; hybrid/Phyrexian are not fractional.
        n = (
            sum("R" in sym.split("/") for sym in re.findall(r"\{([^}]+)\}", infos[0][1].mana_cost))
            if len(infos) == 1
            else 0
        )
    else:
        return run_other(plan, ctx, e, infos)
    follow = replace_x(e["recipe"], n)
    i = ctx["next"]
    ctx["effects"][i:i] = follow
    return True


def run_other(
    plan: Plan, ctx: dict[str, Any], e: dict[str, Any], infos: list[tuple[CardInstance, Characteristics]]
) -> bool:
    from app.rules import scripts, selectors

    mode = e["mode"]
    follow: list[dict[str, Any]] = []
    if mode == "destroy_same_mv" and len(infos) == 1:
        sel = selectors.Selector(types=("Creature",), compare=(("mv", "==", int(infos[0][1].mana_value)),))
        follow = [{"do": "destroy", "who": sel.key()}]
    elif mode == "destroy_shared_creature_type" and len(infos) == 1:
        kinds = tuple(sorted(infos[0][1].subtypes & selectors.CREATURE_TYPES))
        if kinds:
            follow = [
                {"do": "destroy", "who": selectors.Selector(types=("Creature",), subtypes=kinds).key()},
                {"do": "no_regen"},
            ]
    elif mode == "discard_shared_color":
        follow = [{"do": "reveal_hand", "who": "target"}]
        colors = tuple(sorted(infos[0][1].colors)) if len(infos) == 1 else ()
        if colors:
            follow.append(
                {
                    "do": "discard_named",
                    "who": "revealed",
                    "sel": selectors.Selector(zones=(), card=True, colors=colors).key(),
                }
            )
    elif mode == "three_paid_types":
        if len({kind for _, ch in infos for kind in ch.types}) >= 3:
            native = scripts.parse_effects("Each opponent loses 3 life. You gain 3 life. Draw three cards.")
            assert native is not None
            follow = native[0]
    elif mode == "pyre" and len(infos) == 1:
        native = scripts.parse_effects(
            "Search your library for a creature card with mana value equal to 1 plus the sacrificed creature's mana value, put it onto the battlefield, then shuffle."
        )
        assert native is not None
        follow = native[0]
        sel = selectors.from_key(follow[0]["sel"])
        kinds = tuple(sorted(infos[0][1].subtypes & selectors.CREATURE_TYPES))
        follow[0]["sel"] = selectors.replace(
            sel, subtypes=kinds, not_types=() if kinds else ("Creature",)
        ).key()
    elif mode == "conditional_return" and len(infos) == 1:
        from app.rules import effects

        targets = effects._cards(plan, ctx, "target")
        if (
            targets
            and (pt := plan.ch(plan.state.cards[targets[0]]).pt) is not None
            and pt[0] <= power(infos[0][1])
        ):
            follow = [
                {"do": "return_card", "who": "target", "to": "battlefield", "tapped": False, "under": "you"}
            ]
    elif mode == "suspected_draw":
        from app.rules import context

        refs = context.refs(ctx).get(e["as"], {}).get("objects", [])
        snap = plan.rules.lki.get(refs[0]["object_id"]) if len(refs) == 1 else None
        if snap is None or snap.suspected is None:
            return legacy(plan, ctx)
        follow = [{"do": "draw", "who": "you", "n": 2 if snap.suspected else 1}]
    elif mode == "anchor_compare" and len(infos) == 1:
        from app.rules import context

        found_key = e["found_ref"].removeprefix("ref:")
        binding = context.refs(ctx).get(found_key, {})
        current_key = found_key + ":current"
        context.refs(ctx)[current_key] = {
            "kind": "objects",
            "objects": binding.get("moved") or binding.get("objects") or [],
        }
        found = context.infos(plan, ctx, current_key)
        if found and found[0][1].mana_value < infos[0][1].mana_value:
            follow = [{"do": "scry", "who": "you", "n": 2}]
    i = ctx["next"]
    ctx["effects"][i:i] = follow
    return True


def legacy(plan: Plan, ctx: dict[str, Any], prompt: str | None = None) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    decide(
        plan,
        player=ctx["controller"],
        kind="manual_resolution",
        prompt=prompt
        or "This older save did not record whether the sacrificed creature was suspected. Draw one or two cards as appropriate by hand, then press Done.",
        options=[DecisionOption(id="done", label="Done")],
        resume={"step": "paid_sacrifice_legacy_done", "ctx": ctx},
    )
    return False


def legacy_done(plan: Plan, d: Decision, chosen: list[str]) -> None:
    from app.rules import effects

    if d.resume is None:
        raise ValueError("A saved sacrifice continuation needs its resolution context")
    effects.continue_effects(plan, d.resume["ctx"])


def definition(ability: AbilityText, ch: Characteristics) -> Definition | None:
    from dataclasses import replace

    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if (
        ability.kind != "triggered"
        or text
        != "When ~ enters, create a 2/2 white Alien creature token. If ~'s emerge cost was paid, instead create X of those tokens, where X is the sacrificed creature's toughness."
    ):
        return None
    native = scripts.define(
        replace(ability, text="When ~ enters, create a 2/2 white Alien creature token."), ch
    )
    if native is None:
        return None
    native["effects"] = [{"do": "source_emerge_tokens", "recipe": native["effects"]}]
    return native


def source_emerge_tokens(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules.triggers import _snapshot_card

    paid = plan.rules.payments.get(ctx.get("source_object") or "")
    n = 1
    if paid is not None and paid.alternative == "emerge":
        snaps = [plan.rules.lki.get(oid) for oid in paid.sacrificed_objects]
        snap = snaps[0] if len(snaps) == 1 else None
        if snap is None:
            return legacy(
                plan,
                ctx,
                "This older save did not retain the emerge sacrifice. Create the appropriate number of Alien tokens by hand, then press Done.",
            )
        n = max(0, toughness(_snapshot_card(plan, snap)[1]))
    follow = copy.deepcopy(e["recipe"])
    for item in follow:
        if item.get("do") == "create_token":
            item["n"] = n
    i = ctx["next"]
    ctx["effects"][i:i] = follow
    return True


RESUME = {"paid_sacrifice_legacy_done": legacy_done}


def power(ch: Characteristics) -> int:
    from app.rules import values

    return values._stat_of(ch, "power") or 0


def toughness(ch: Characteristics) -> int:
    from app.rules import values

    return values._stat_of(ch, "toughness") or 0
