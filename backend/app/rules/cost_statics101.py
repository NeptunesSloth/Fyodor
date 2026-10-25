"""Native cost statics for chosen-source taxes and commander/stack identities."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import CardInfo, Characteristics
    from app.rules.oracle import AbilityText

MYTH = "Your commander costs {1} less to cast for each time it's been cast from the command zone this game."
LIESA = "Rather than pay {2} for each previous time you've cast this spell from the command zone this game, pay 2 life that many times."
TORCH = "As long as ~ is on the stack, spells that target it cost {2} more to cast."


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    text = scripts.self_text(ability.text, ch.name)
    if text == MYTH:
        return {
            "kind": "static",
            "static": "cost_modifier",
            "delta": -1,
            "caster": "any",
            "filter": None,
            "commander_history101": True,
            "effects": [],
        }
    if text == LIESA:
        return {"kind": "static", "static": "commander_tax_life101", "effects": []}
    if text == TORCH:
        return {
            "kind": "static",
            "static": "cost_modifier",
            "delta": 2,
            "caster": "any",
            "filter": None,
            "stack_target101": True,
            "effects": [],
        }
    if text == "Whenever your commander is put into the command zone from anywhere, draw a card.":
        native = scripts.define(
            replace(
                ability,
                text="Whenever a creature card is put into your graveyard from anywhere, draw a card.",
            ),
            ch,
        )
        assert native is not None
        return {
            **native,
            "cond": {
                "event": "to_command",
                "subject": "sel",
                "aggregate": False,
                "sel": selectors.Selector(card=True, commander=True, owner="you", zones=()).key(),
            },
        }
    return None


def commander_life(state: GameState, card: CardInstance, ch: Characteristics) -> int:
    from app.rules import scripts

    if not card.commander_key or card.zone != f"{card.owner}:command":
        return 0
    if not any(d.get("static") == "commander_tax_life101" for d in scripts.definitions(ch).values()):
        return 0
    return 2 * state.players[card.owner].commander_casts.get(card.commander_key, 0)


def replaces_commander_tax(card: CardInstance, ch: Characteristics) -> bool:
    from app.rules import scripts

    return bool(
        card.commander_key
        and card.zone == f"{card.owner}:command"
        and any(d.get("static") == "commander_tax_life101" for d in scripts.definitions(ch).values())
    )


def stack_statics(state: GameState, info: CardInfo) -> list[tuple[CardInstance, int, dict[str, Any]]]:
    from app.rules import scripts
    from app.rules.plan import Plan

    view = None
    out = []
    for card in state.cards.values():
        if card.zone != "stack" or card.ability is not None:
            continue
        view = view or Plan.view(state, card.controller, info)
        for index, d in scripts.definitions(view.ch(card)).items():
            if d.get("stack_target101"):
                out.append((card, index, d))
    return out
