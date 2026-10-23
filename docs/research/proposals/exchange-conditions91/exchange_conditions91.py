"""Follow-up clauses of exact native permanent-control exchanges."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

MODIFY = "Exchange control of two target creatures controlled by different players. If you control neither creature, draw three cards."
GAUNTLETS = "{5}, Sacrifice this artifact: Exchange control of target artifact, creature, or land you control and target permanent an opponent controls that shares one of those types with it. If those permanents are exchanged this way, destroy all Auras attached to them."

DRAKE = "When ~ enters, exchange control of ~ and up to one target creature an opponent controls. If you don't or can't make an exchange, sacrifice ~. This ability still resolves if its target becomes illegal."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    text = scripts.self_text(ability.text, ch.name)
    if text == MODIFY:
        native = scripts.define(replace(ability, text=MODIFY.split(". If")[0] + "."), ch)
        if native:
            return {
                **native,
                "effects": [*native["effects"], {"do": "exchange_neither91"}],
            }
    if text == GAUNTLETS.replace("this artifact", "~"):
        native = scripts.define(
            replace(
                ability,
                text="{5}, Sacrifice this artifact: Exchange control of target artifact or creature and another target permanent that shares one of those types with it.",
            ),
            ch,
        )
        if native:
            first = selectors.parse("artifact, creature, or land you control")
            second = selectors.parse("permanent an opponent controls")
            assert first is not None and second is not None
            specs = native["targets"]
            return {
                **native,
                "targets": [
                    {**specs[0], "what": first.key()},
                    {
                        **specs[1],
                        "what": second.key(),
                        "relative_quality": {
                            "kind": "types",
                            "types": ["Artifact", "Creature", "Land"],
                        },
                    },
                ],
                "effects": [
                    {**native["effects"][0], "as": "exchanged91"},
                    {"do": "exchange_auras91"},
                ],
            }
    if text == DRAKE:
        native = scripts.define(
            replace(
                ability,
                text="When this creature enters, exchange control of this creature and target creature an opponent controls.",
            ),
            ch,
        )
        if native:
            return {
                **native,
                "target": None,
                "targets": [{**native["target"], "min": 0, "max": 1}],
                "effects": [{"do": "exchange_drake91"}],
            }
    return None


def resolves_illegal(entry: Any) -> bool:
    return entry.kind == "trigger" and entry.effects == [{"do": "exchange_drake91"}]


def drake(plan: Any, ctx: Any, effect: Any) -> bool:
    from app.rules import context, effects

    effects.exchange_control(plan, ctx, {"who": "self", "with": "target", "as": "drake91"})
    if len(context.objects(plan, ctx, "drake91")) != 2:
        return effects.sacrifice(plan, ctx, {"who": "self"})
    return True


def neither(plan: Any, ctx: Any, effect: Any) -> bool:
    from app.rules import effects

    # 608.2b: an illegal target cannot supply information for the independent condition.
    cards = effects._cards(plan, ctx, "target:0")
    if len(cards) != 2:
        return True
    if not any(plan.state.cards[c].controller == ctx["controller"] for c in cards):
        return effects.draw(plan, ctx, {"do": "draw", "who": "you", "n": 3})
    return True


def auras(plan: Any, ctx: Any, effect: Any) -> bool:
    from app.rules import context, effects

    exchanged = context.objects(plan, ctx, "exchanged91")
    if len(exchanged) != 2:
        return True
    ids = [
        c.id
        for c in plan.state.cards.values()
        if c.zone.endswith(":battlefield")
        and plan.in_game(c)
        and c.attached_to in exchanged
        and "Aura" in plan.ch(c).subtypes
    ]
    return effects._destroy_cards(plan, ctx, {}, ids)
