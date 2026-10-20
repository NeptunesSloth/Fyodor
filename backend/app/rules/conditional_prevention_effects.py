"""Conditional prevention reads quantities and source relations at their rules-defined time."""

from __future__ import annotations

from dataclasses import replace as dc_replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = "conditional_prevention"


def _static(source: dict[str, Any], to: dict[str, Any], op: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "static",
        "static": "replace",
        "event": "damage",
        "match": {"source": source, "to": to},
        "op": {**op, "prevention": True},
        "effects": [],
    }


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, values
    from app.rules.nontarget_creature_choices import key

    text = scripts.self_text(ability.text, ch.name)
    cases = {
        "If a source would deal damage to equipped creature, prevent X of that damage, where X is the number of creatures you control.": _static(
            {},
            {"objects": {"attached": True}},
            {"do": "prevent", "n": 0, "value": values.parse_count("creatures you control")},
        ),
        "If a spell would deal damage to a permanent or player, prevent 1 damage that spell would deal to that permanent or player.": _static(
            {"spell": True}, {}, {"do": "prevent", "n": 1}
        ),
        "Prevent all damage that would be dealt to a creature by another creature if they share a color.": _static(
            {"types": ["Creature"], "shares_recipient_color": True},
            {"objects": {"sel": key("creature")}},
            {"do": "prevent_all"},
        ),
        "As long as you control another creature, prevent all damage that would be dealt to ~ by spells that target it.": _static(
            {"spell": True, "targets_holder_with_other_creature": True},
            {"objects": {"self": True}},
            {"do": "prevent_all"},
        ),
    }
    if ability.kind == "static" and text in cases:
        return cases[text]
    if (
        ability.kind == "static"
        and text == "If a source would deal 3 or less damage to ~, prevent that damage."
    ):
        d = _static({}, {"objects": {"self": True}}, {"do": "prevent_all"})
        d["match"]["below_value"] = 4
        return d
    # A source-counter cost makes the otherwise unbound "it" refer to this source.
    if (
        ability.kind == "activated"
        and ability.cost
        and text
        == "Remove a +1/+0 counter from ~: Prevent the next 1 damage that would be dealt to it this turn."
    ):
        cost = scripts.parse_ability_cost(ability.cost, card_name=ch.name)
        if not cost.unsupported and cost.remove_counters == (("+1/+0", 1),):
            return scripts.define(
                dc_replace(ability, text=text.replace("to it this turn", "to ~ this turn")), ch
            )
    return None


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    text = body.strip()
    text = text[:1].upper() + text[1:]
    if (
        text
        == "Prevent all damage that would be dealt to you this turn by a source of your choice that shares a color with the mana spent on this activation cost."
    ):
        return ([{"do": STEP, "mode": "paid_color"}], None, False)
    if (
        text
        == "Prevent all damage that would be dealt this turn by a source of your choice that shares a color with the exiled card."
    ):
        return ([{"do": STEP, "mode": "linked_color"}], None, False)
    if (
        text
        == "Choose a permanent you control. Prevent all combat damage target creature would deal this turn if it shares a color with that permanent."
    ):
        return (
            [
                {
                    "do": "return_choice",
                    "sel": _key("permanent you control"),
                    "n": 1,
                    "to": "choose",
                    "as": "prevent_color_permanent",
                },
                {"do": STEP, "mode": "guard"},
            ],
            "creature",
            False,
        )
    if (
        text
        == "The next time a creature of your choice with shadow would deal damage to you this turn, prevent that damage."
    ):
        return (
            [
                {
                    "do": "return_choice",
                    "sel": _key("creature with shadow"),
                    "n": 1,
                    "to": "choose",
                    "as": "prevent_shadow_source",
                },
                {
                    "do": "source_shield",
                    "src": "ref:prevent_shadow_source",
                    "props": {"types": ["Creature"], "keywords": ["shadow"]},
                    "to": "you",
                    "once": True,
                },
            ],
            None,
            False,
        )
    if (
        text
        == "Prevent the next 2 damage that would be dealt to any target this turn. If this spell was kicked, prevent the next 4 damage that would be dealt to that permanent or player this turn instead."
    ):
        return ([{"do": STEP, "mode": "orim"}], "any", False)
    if (
        text
        == "Prevent the next 1 damage that would be dealt to any target this turn. If it's a green creature, prevent the next 2 damage instead."
    ):
        return ([{"do": STEP, "mode": "healer"}], "any", False)
    if (
        text
        == "Prevent the next 3 damage that would be dealt this turn to any number of targets, divided as you choose. If this spell was kicked, prevent the next 6 damage this way instead."
    ):
        base = scripts.parse_effects(
            "Prevent the next 3 damage that would be dealt this turn to any number of targets, divided as you choose."
        )
        assert base is not None
        target = base[1][0]
        groups = [
            {
                **target,
                "min": 0,
                "max": n,
                "kicked": flag,
                "divide": {"what": "damage", "total": n, "allow_zero_targets": True},
            }
            for flag, n in [(False, 3), (True, 6)]
        ]
        return (
            [
                {"do": "prevent", "who": "target:0", "n": {"divided": 0}},
                {"do": "prevent", "who": "target:1", "n": {"divided": 1}},
            ],
            groups,
            False,
        )
    if (
        text
        == "Tap all blocking creatures. Prevent all combat damage that would be dealt this turn. Each attacking creature and each blocking creature doesn't untap during its controller's next untap step."
    ):
        return ([{"do": STEP, "mode": "spore"}], None, False)
    return None


def _key(text: str) -> str:
    from app.rules.nontarget_creature_choices import key

    return key(text)


def source_matches(plan: Plan, spec: dict[str, Any], candidate: Any, ev: dict[str, Any]) -> bool:
    from app.rules import exiled_with, selectors

    src = ev.get("src") or {}
    if spec.get("keywords") and not set(spec["keywords"]) <= set(src.get("keywords") or []):
        return False
    if spec.get("shares_recipient_color"):
        target = plan.state.cards.get(ev.get("target") or "")
        if (
            target is None
            or plan.oid(target) == ev.get("source_oid")
            or not set(src.get("colors") or []) & plan.ch(target).colors
        ):
            return False
    if spec.get("targets_holder_with_other_creature"):
        holder = plan.state.cards.get(candidate.source_card or "")
        spell = plan.rules.stack.get(ev.get("source_card") or "")
        if holder is None or spell is None:
            return False
        refs = [
            *spell.targets,
            *(r for group in spell.groups for r in group),
            *(r for slot in spell.slots for r in slot),
        ]
        if not any(r.object_id == plan.oid(holder) for r in refs):
            return False
        if not any(
            cid != holder.id
            for cid in selectors.candidates(
                plan, selectors.from_key(_key("creature you control")), candidate.controller, holder.id
            )
        ):
            return False
    if link := spec.get("shares_linked_colors"):
        cards = exiled_with.cards(plan, link)
        colors = {color for cid in cards for color in plan.ch(plan.state.cards[cid]).colors}
        if not colors & set(src.get("colors") or []):
            return False
    return True


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects, exiled_with, selectors, source_shields

    mode = e["mode"]
    if mode in ("paid_color", "linked_color"):
        props: dict[str, Any] = {}
        extra: dict[str, Any] = {}
        if mode == "paid_color":
            stack_id = ctx.get("stack_id") or ""
            record = plan.rules.payments.get(plan.oid(stack_id)) if stack_id in plan.state.cards else None
            colors = [
                color
                for color, n in (record.mana_spent.items() if record is not None else [])
                if color in "WUBRG" and n > 0
            ]
        else:
            link: dict[str, Any] = {
                k: ctx[k]
                for k in ("source_card", "source_object", "controller", "borrowed_link_scope")
                if k in ctx
            }
            linked = exiled_with.cards(plan, link)
            colors = sorted({color for cid in linked for color in plan.ch(plan.state.cards[cid]).colors})
            extra["record_props"] = {"shares_linked_colors": link}
        if not colors:
            return True  # Colorless is no color; an empty set is never a wildcard.
        props["colors"] = colors
        return source_shields.source_shield(
            plan, ctx, {"props": props, "to": "you" if mode == "paid_color" else None, **extra}
        )
    if mode == "guard":
        target = effects._cards(plan, ctx, "target")
        chosen = context.objects(plan, ctx, "prevent_color_permanent")
        if (
            target
            and chosen
            and plan.ch(plan.state.cards[target[0]]).colors & plan.ch(plan.state.cards[chosen[0]]).colors
        ):
            return source_shields.source_shield(
                plan, ctx, {"src": "target", "props": {}, "combat": True, "to": None}
            )
        return True
    if mode in ("orim", "healer"):
        if mode == "orim":
            paid = plan.rules.payments.get(ctx.get("source_object") or "")
            n = 4 if paid is not None and paid.kicked else 2
        else:
            target = effects._cards(plan, ctx, "target")
            n = (
                2
                if target and (ch := plan.ch(plan.state.cards[target[0]])).is_creature and "G" in ch.colors
                else 1
            )
        return effects.prevent(plan, ctx, {"who": "target", "n": n})
    if mode == "spore":
        combat = selectors.candidates(
            plan,
            selectors.from_key(_key("attacking or blocking creatures")),
            ctx["controller"],
            ctx.get("source_card"),
        )
        blockers = [
            cid for cid in combat if plan.state.cards[cid].is_blocking
        ]
        context.bind_objects(plan, ctx, "spore_blockers", blockers)
        context.bind_objects(plan, ctx, "spore_combatants", combat)
        at = int(ctx.get("next") or 0)
        ctx["effects"][at:at] = [
            {"do": "tap", "who": "ref:spore_blockers"},
            {"do": "prevent_all", "scope": {"combat": True, "any_target": True}},
            {"do": "stay_tapped", "who": "ref:spore_combatants"},
        ]
        return True
    raise ValueError(mode)


PRIMITIVES = {STEP: run}
