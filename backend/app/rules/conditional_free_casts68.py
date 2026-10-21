"""Conditional zero-mana casting authority composed from native permissions."""

from __future__ import annotations

import secrets
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import cast_limits, permissions, scripts, selectors

    text = scripts.self_text(ability.text, ch.name)
    base = permissions.define_static(
        "You may cast spells from your hand without paying their mana costs.", "static"
    )
    if base is None:
        return None
    if (
        text
        == "You may cast spells with mana value less than or equal to the number of creatures you control from your hand without paying their mana costs."
    ):
        creatures = selectors.Selector(types=("Creature",), controller="you").key()
        return {**base, "free68_ceiling": {"count": creatures}}
    if (
        text
        == "You may cast spells with mana value less than or equal to the number of lands you control without paying their mana costs."
    ):
        lands = selectors.Selector(types=("Land",), controller="you").key()
        return {**base, "zone": "any", "free68_ceiling": {"count": lands}}
    if (
        text
        == "Any player may cast creature spells with mana value 3 or less without paying their mana costs and as though they had flash."
    ):
        creatures = selectors.Selector(
            zones=("stack",), types=("Creature",), compare=(("mv", "<=", 3),)
        ).key()
        return {
            **base,
            "zone": "any",
            "filter": creatures,
            "any_player": True,
            "flash": True,
            "flash_requires_free": True,
        }
    if (
        text
        == "Once during each of your turns, you may cast a noncreature or Robot spell from your hand without paying its mana cost."
    ):
        union = selectors.Selector(
            zones=("stack",),
            either=(
                selectors.Selector(zones=("stack",), not_types=("Creature",)).key(),
                selectors.Selector(zones=("stack",), subtypes=("Robot",)).key(),
            ),
        ).key()
        return {**base, "filter": union, "once": True}
    if (
        text
        == "The first spell each player casts during each of their turns may be cast without paying its mana cost."
    ):
        return {
            **base,
            "zone": "any",
            "any_player": True,
            "during": "your_turn",
            "first": True,
        }
    if (
        text
        == "If this spell is the first spell you've cast this game, you may cast it without paying its mana cost."
    ):
        return {**base, "self": True, "free68_first_game": True}
    if (
        text
        == "You can cast spells only during your turn and you can cast no more than two spells each turn."
    ):
        own = cast_limits.static_definition(
            "Players can cast spells only during their own turns."
        )
        limit = cast_limits.static_definition(
            "Each player can't cast more than one spell each turn."
        )
        if own is None or limit is None:
            return None
        return {**own, "who": "you", "also": [{**limit, "who": "you", "max": 2}]}
    if (
        text
        == "I — The next red or green creature spell you cast this turn can be cast without paying its mana cost."
    ):
        native = scripts.define(replace(ability, text="I — Draw a card."), ch)
        matching = selectors.Selector(
            zones=("stack",), types=("Creature",), colors=("R", "G")
        ).key()
        return (
            {**native, "effects": [{"do": "next_free_cast68", "filter": matching}]}
            if native is not None
            else None
        )
    return None


def eligible(
    state: Any, info: Any, player: str, card: Any, ch: Any, definition: dict[str, Any]
) -> bool:
    from app.rules import permissions, values

    if (
        definition.get("free68_first_game")
        and state.rules.cast_history_complete is not True
    ):
        return False
    if definition.get("free68_first_game") and (
        any(state.rules.named_casts_game.get(player, {}).values())
        or any(note.player == player for note in state.rules.turn_log.casts)
    ):
        return False
    ceiling = definition.get("free68_ceiling")
    if ceiling is None:
        return True
    return ch.mana_value <= values.evaluate(
        permissions._view(state, player, info), {"controller": player}, ceiling
    )


def next_free(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.game.rules_state import Permission
    from app.rules.cost_changes import casts_so_far

    player, matching = ctx["controller"], effect["filter"]
    plan.rules.permissions.append(
        Permission(
            id=secrets.token_hex(4),
            player=player,
            cast=True,
            zone="any",
            filter=matching,
            nth=casts_so_far(plan.state, plan.info, player, matching),
            free=True,
            until="end_of_turn",
            turn=plan.state.turn.number,
            source=ctx.get("source_object"),
            label=f"{ctx.get('name', 'An effect')}: next matching spell without paying its mana cost",
        )
    )
    return True
