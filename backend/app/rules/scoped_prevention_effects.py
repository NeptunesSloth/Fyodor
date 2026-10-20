"""Timed prevention scopes compose native damage records and shared shield budgets."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = "scoped_prevention"


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts, selectors
    from app.rules.nontarget_creature_choices import key

    text = body.strip()
    text = text[:1].upper() + text[1:]
    if (
        text
        == "Until your next turn, prevent all damage that would be dealt to and dealt by target permanent an opponent controls."
    ):
        return (
            [
                {
                    "do": "prevent_all",
                    "scope": {"combat": None, "to_or_by": True},
                    "who": "target",
                    "role": "both",
                    "duration": "next_turn",
                }
            ],
            key("permanent an opponent controls"),
            False,
        )
    if (
        text
        == "Untap any number of target creatures. Prevent all combat damage that would be dealt to and dealt by those creatures this turn."
    ):
        parsed = scripts.parse_effects("Untap any number of target creatures.")
        assert parsed is not None
        return (
            [
                *parsed[0],
                {
                    "do": "prevent_all",
                    "scope": {"combat": True, "to_or_by": True},
                    "who": "target:0",
                    "role": "both",
                },
            ],
            parsed[1],
            False,
        )
    if (
        text
        == "Prevent all combat damage that would be dealt by creatures other than target creature this turn."
    ):
        return ([{"do": STEP, "mode": "except_target"}], "creature", False)
    if (
        text
        == "Transform all Humans. Prevent all combat damage that would be dealt this turn by creatures other than Werewolves and Wolves."
    ):
        return (
            [
                {"do": "transform", "who": key("Human creatures")},
                {
                    "do": STEP,
                    "mode": "class",
                    "props": {"types": ["Creature"], "not_subtypes": ["Werewolf", "Wolf"]},
                },
            ],
            None,
            False,
        )
    if (
        text
        == "Prevent all combat damage that would be dealt this turn except combat damage that would be dealt by enchanted creatures and enchantment creatures. Scry 2."
    ):
        return (
            [
                {
                    "do": STEP,
                    "mode": "class",
                    "props": {"types": ["Creature"], "not_enchanted_or_enchantment": True},
                },
                {"do": "scry", "n": 2, "who": "you"},
            ],
            None,
            False,
        )
    if (
        text
        == "Tap all creatures blocking target attacking creature. Prevent all combat damage that would be dealt this turn by that creature and each creature blocking it."
    ):
        return ([{"do": STEP, "mode": "feint"}], "attacking_creature", False)
    if (
        text
        == "Choose target creature. If it's attacking, it can't be blocked this turn. If it's blocking, prevent all combat damage that would be dealt this combat by it and each creature it's blocking."
    ):
        return ([{"do": STEP, "mode": "sewers"}], "creature", False)
    if (
        text
        == "Prevent all damage that would be dealt to target tapped Merfolk or Kithkin creature this turn."
    ):
        what = selectors.Selector(types=("Creature",), subtypes=("Merfolk", "Kithkin"), tapped=True).key()
        return (
            [{"do": "prevent_all", "scope": {"combat": None}, "who": "target", "role": "to"}],
            what,
            False,
        )
    if text in (
        "Prevent all combat damage that would be dealt to ~ this turn.",
        "Prevent all combat damage that would be dealt to this creature this turn.",
    ):
        return ([{"do": "prevent_all", "scope": {"combat": True}, "who": "self", "role": "to"}], None, False)
    if (
        text
        == "Prevent the next 1 damage that would be dealt to target player, planeswalker, or Sliver creature this turn."
    ):
        what = "player_planeswalker_or_sliver"
        return ([{"do": "prevent", "who": "target", "n": 1}], what, False)
    if text == "Prevent the next 1 combat damage that would be dealt to you this turn.":
        return (
            [{"do": "source_shield", "src": "class", "props": {}, "combat": True, "to": "you", "budget": 1}],
            None,
            False,
        )
    if text == "Prevent the next 1 damage that would be dealt by ~ this turn.":
        return ([{"do": "source_shield", "src": "self", "props": {}, "to": None, "budget": 1}], None, False)
    if (
        text
        == "Prevent the next 3 damage that would be dealt to any target this turn by a source of your choice. You gain 3 life."
    ):
        return (
            [
                {"do": "source_shield", "props": {}, "to": "target", "budget": 3},
                {"do": "gain_life", "who": "you", "n": 3},
            ],
            "any",
            False,
        )
    if (
        text
        == "You gain life equal to target creature's power. The next time that creature would deal damage this turn, prevent that damage."
    ):
        parsed = scripts.parse_effects("You gain life equal to target creature's power.")
        assert parsed is not None
        return (
            [*parsed[0], {"do": "source_shield", "src": "target", "props": {}, "to": None, "once": True}],
            parsed[1],
            False,
        )
    if text == "Prevent all combat damage a creature of your choice would deal this turn.":
        return ([{"do": STEP, "mode": "choose_creature", "props": {}, "combat": True}], None, False)
    if text == "Prevent all damage target spell would deal this turn.":
        return ([{"do": STEP, "mode": "spell_source"}], "spell", False)
    if (
        text
        == "The next time an unblocked creature of your choice would deal combat damage to you this turn, prevent all but 1 of that damage."
    ):
        return (
            [
                {
                    "do": STEP,
                    "mode": "choose_creature",
                    "props": {"sel": key("unblocked creature")},
                    "combat": True,
                    "once": True,
                    "cap": 1,
                    "to": "you",
                }
            ],
            None,
            False,
        )
    return None


def source_matches(plan: Plan, spec: dict[str, Any], ev: dict[str, Any]) -> bool:
    """Only opt-in predicates beyond the existing source matcher."""
    if not any(spec.get(flag) for flag in ("except_oids", "not_enchanted_or_enchantment", "combat_related")):
        return True
    source = plan.state.cards.get(ev.get("source_card") or "")
    same = (
        source is not None
        and source.zone.endswith(":battlefield")
        and plan.oid(source) == ev.get("source_oid")
    )
    if spec.get("except_oids") and ev.get("source_oid") in spec["except_oids"]:
        return False
    if spec.get("not_enchanted_or_enchantment"):
        if "Enchantment" in (ev.get("src") or {}).get("types", []):
            return False
        if (
            source is not None
            and same
            and any(
                c.attached_to == source.id
                and c.zone.endswith(":battlefield")
                and "Aura" in plan.ch(c).subtypes
                for c in plan.state.cards.values()
            )
        ):
            return False
    if relation := spec.get("combat_related"):
        if ev.get("source_oid") == relation["oid"]:
            return True
        anchor = next(
            (
                c
                for c in plan.state.cards.values()
                if c.zone.endswith(":battlefield") and plan.oid(c) == relation["oid"]
            ),
            None,
        )
        if source is None or not same or anchor is None:
            return False
        if relation["kind"] == "blocks":
            return source.blocks(anchor.id)
        return anchor.blocks(source.id)
    return True


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects, replace, source_shields
    from app.rules.nontarget_creature_choices import key

    mode = e["mode"]
    if mode == "choose_creature":
        # A creature of your choice is a permanent (109.2), not a creature spell.
        at = int(ctx.get("next") or 0)
        shield: dict[str, Any] = {
            "do": "source_shield",
            "src": "ref:prevent_source",
            "props": e["props"],
            "to": e.get("to"),
            "combat": True,
        }
        shield.update({k: e[k] for k in ("once", "cap") if k in e})
        ctx["effects"][at:at] = [
            {
                "do": "return_choice",
                "sel": key("unblocked creature" if e.get("cap") else "creature"),
                "n": 1,
                "to": "choose",
                "as": "prevent_source",
            },
            shield,
        ]
        return True
    if mode == "spell_source":
        mine = effects._cards(plan, ctx, "target")
        if mine:
            oid = plan.oid(mine[0])
            options = source_shields.choosable(plan, {})
            covered = next((oids for _, oids, _ in options if oid in oids), [oid])
            source_shields._record(plan, ctx, {"props": {}, "to": None}, covered, "")
        return True
    if mode == "class":
        return source_shields.source_shield(
            plan, ctx, {"src": "class", "props": e["props"], "combat": True, "to": None}
        )
    mine = effects._cards(plan, ctx, "target")
    if not mine:
        return True
    card = plan.state.cards[mine[0]]
    if mode == "except_target":
        return source_shields.source_shield(
            plan,
            ctx,
            {
                "src": "class",
                "props": {"types": ["Creature"], "except_oids": [plan.oid(card)]},
                "combat": True,
                "to": None,
            },
        )
    if mode == "feint":
        blockers = [
            c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.blocks(card.id)
        ]
        context.bind_objects(plan, ctx, "prevent_blockers", blockers)
        effects.tap(plan, ctx, {"who": "ref:prevent_blockers"})
        kind = "blocks"
    elif mode == "sewers":
        if card.is_attacking:
            effects.restrict(plan, ctx, {"who": "target", "rules": ["unblockable"]})
        if not card.is_blocking:
            return True
        kind = "blocked_by"
    else:
        raise ValueError(mode)
    replace.add_record(
        plan,
        event="damage",
        match={"combat": True, "source": {"combat_related": {"oid": plan.oid(card), "kind": kind}}, "to": {}},
        op={"do": "prevent_all", "prevention": True},
        controller=ctx["controller"],
        source=ctx.get("source_object"),
        source_card=ctx.get("source_card"),
        label=ctx.get("name") or "Prevention",
        **({"until": "end_of_combat"} if mode == "sewers" else {}),
    )
    return True


PRIMITIVES = {STEP: run}
