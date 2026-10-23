"""Exact top-library authorities reuse native additional costs and selected-use receipts."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import permissions, scripts, selectors

    text = scripts.self_text(ability.text, ch.name)
    lines = tuple(a.text for a in ch.abilities)
    if (
        text
        == "Whenever ~ attacks, create a Treasure token. Until end of turn, you may look at the top card of your library any time, and you may play lands and cast spells from the top of your library."
    ):
        native = scripts.define(
            replace(ability, text="Whenever " + ch.name + " attacks, create a Treasure token."), ch
        )
        return (
            {**native, "effects": [*native["effects"], {"do": "grant_top69"}]} if native is not None else None
        )
    if (
        text
        == "You may cast spells from the top of your library by removing a counter from a creature you control in addition to paying their other costs."
    ):
        native = permissions.define_static(
            "You may cast spells from the top of your library.", "static", lines
        )
        return (
            {**native, "extra": "Remove a counter from a creature you control"}
            if native is not None
            else None
        )
    if text in (
        "You may cast spells from the top of your library by sacrificing a nonland permanent in addition to paying their other costs.",
    ):
        native = permissions.define_static(
            "You may cast spells from the top of your library.", "static", lines
        )
        extra = "Sacrifice a nonland permanent"
        return {**native, "extra": extra} if native is not None else None
    if text == "You may play snow lands and cast snow spells from the top of your library.":
        native = permissions.define_static(
            "You may play lands and cast spells from the top of your library.", "static", lines
        )
        snow = selectors.Selector(zones=("stack",), supertypes=("Snow",)).key()
        return {**native, "filter": snow, "land_filter": snow} if native is not None else None
    if (
        text
        == "Whenever another snow permanent you control enters, you may pay {G}, {W}, or {U}. If you do, put a +1/+1 counter on ~."
    ):
        native = scripts.define(replace(ability, text=ability.text.replace("{G}, {W}, or {U}", "{G}")), ch)
        if native is None or not any(e.get("do") == "optional_payment" for e in native.get("effects", ())):
            return None
        effects = [
            {**{k: v for k, v in effect.items() if k != "cost"}, "alts": ["{G}", "{W}", "{U}"]}
            if effect.get("do") == "optional_payment"
            else effect
            for effect in native["effects"]
        ]
        return {**native, "effects": effects}
    if (
        text
        == "Once each turn, you may play a historic land or cast a historic spell from the top of your library. When you do, create a Food token."
    ):
        native = permissions.define_static(
            "Once each turn, you may cast a historic spell from the top of your library.", "static", lines
        )
        return (
            {**native, "play": True, "land_filter": "historic", "use_trigger": "create_food69"}
            if native is not None
            else None
        )
    return None


def grant_top(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import permissions

    return permissions.grant_play(
        plan,
        ctx,
        {
            "do": "grant_play",
            "zone": "library_top",
            "play": True,
            "cast": True,
            "until": "end_of_turn",
            "look_top": True,
        },
    )


PRIMITIVES = {"grant_top69": grant_top}
