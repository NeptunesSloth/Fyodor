"""Noncopiable entry forms, applied by native layers before entry replacements and ETBs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import ContinuousEffect, EntryCharacteristics

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.plan import Plan


def freeze(plan: Plan, ctx: dict[str, Any], data: dict[str, Any]) -> EntryCharacteristics:
    """Allocate once in the native entry descriptor, which existing continuations serialize."""
    form = EntryCharacteristics.model_validate(data)
    if form.timestamp:
        return form
    plan.rules.timestamp += 1
    return form.model_copy(
        update={
            "timestamp": plan.rules.timestamp,
            "controller": ctx["controller"],
            "source": ctx.get("source_object"),
            "source_card": ctx.get("source_card"),
            "label": str(ctx.get("name") or "Entry characteristics")[:120],
        }
    )


def probe(card: CardInstance, form: dict[str, Any] | EntryCharacteristics | None) -> CardInstance:
    if form is None or card.is_token:
        return card
    return card.model_copy(update={"entry_characteristics": EntryCharacteristics.model_validate(form)})


def effects(state: GameState, card: CardInstance) -> list[ContinuousEffect]:
    form = card.entry_characteristics
    rules = state.rules
    if form is None or rules is None or not card.zone.endswith(":battlefield") or card.is_token:
        return []
    real = state.cards.get(card.id)
    # A prospective entering copy is newer than all existing effects. Actual entry
    # uses its original object timestamp, never a later attachment/transform stamp.
    sequence = (
        rules.next_object + 1 if real is None or real.zone != card.zone else rules.objects.get(card.id, 0)
    )
    common: dict[str, Any] = {
        "affected": [rules.object_id(card.id)],
        "source": form.source,
        "controller": form.controller or card.controller,
        "timestamp": form.timestamp,
        "object_seq": sequence,
        "duration": "permanent",
        "label": form.label,
    }
    parts: list[tuple[str, dict[str, Any]]] = []
    if form.set_name is not None:
        parts.append(("3", {"set_name": form.set_name}))
    if (
        form.set_types is not None
        or form.add_types
        or form.set_creature_types is not None
        or form.add_subtypes
    ):
        parts.append(
            (
                "4",
                {
                    "set_types": form.set_types,
                    "add_types": form.add_types,
                    "set_creature_types": form.set_creature_types,
                    "add_subtypes": form.add_subtypes,
                },
            )
        )
    if form.set_colors is not None or form.add_colors:
        parts.append(("5", {"set_colors": form.set_colors, "add_colors": form.add_colors}))
    if form.remove_abilities or form.add_abilities or form.add_keywords:
        parts.append(
            (
                "6",
                {
                    "remove_abilities": form.remove_abilities,
                    "add_abilities": form.add_abilities,
                    "add_keywords": form.add_keywords,
                },
            )
        )
    if form.power is not None or form.toughness is not None:
        parts.append(("7b", {"power": form.power, "toughness": form.toughness}))
    return [
        ContinuousEffect.model_validate(
            {**common, "id": f"entry:{form.timestamp}:{layer}", "layer": layer, **change}
        )
        for layer, change in parts
    ]


def from_become(effect: dict[str, Any]) -> dict[str, Any] | None:
    """Only marked is/has riders; ordinary becomes/gains stay after the move."""
    if effect.get("do") == "enters_as":
        return {"set_types": effect["types"]}
    if effect.get("do") != "become" or not effect.get("entry_as") or effect.get("duration") != "permanent":
        return None
    if effect.get("all_creature_types") or effect.get("land_types") or effect.get("supertypes"):
        return None
    return {
        "set_types": None if effect.get("retain") or not effect.get("types") else effect["types"],
        "add_types": effect.get("types", []) if effect.get("retain") else [],
        "set_creature_types": effect.get("creature_types"),
        "add_subtypes": effect.get("add_creature_types", []),
        "set_colors": effect.get("colors"),
        "add_colors": effect.get("add_colors", []),
        "power": effect.get("p"),
        "toughness": effect.get("t"),
        "add_keywords": effect.get("keywords", []),
        "remove_abilities": bool(effect.get("lose_abilities")),
        "add_abilities": effect.get("abilities", []),
    }


def prepare_return(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> dict[str, Any] | None:
    """Hoist once before existing entry continuations; their saved context owns the skipped rider."""
    if effect.get("as") and 0 <= ctx.get("next", -1) < len(ctx.get("effects") or []):
        following = ctx["effects"][ctx["next"]]
        if following.get("who") == f"ref:{effect['as']}" and (form := from_become(following)) is not None:
            effect["entry_characteristics"] = form
            ctx["next"] += 1
    data = effect.get("entry_characteristics")
    if data is None:
        return None
    from app.rules import conditions, effects

    if effect.get("entry_characteristics_if") and not conditions.holds(
        plan, ctx, effect["entry_characteristics_if"]
    ):
        return None
    data = dict(data)
    for stat in ("power", "toughness"):
        if isinstance(data.get(stat), dict):
            data[stat] = effects._amount(plan, ctx, data[stat])
    frozen = freeze(plan, ctx, data).model_dump(mode="json")
    effect["entry_characteristics"] = frozen
    return frozen
