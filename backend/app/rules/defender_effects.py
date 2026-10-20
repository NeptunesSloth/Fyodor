"""Defending-player-relative attack effects using ordinary target/payment primitives."""

from __future__ import annotations

import re
from typing import Any

Parsed = tuple[list[dict[str, Any]], Any, bool]


def parse(body: str, *, it: str | None = None) -> Parsed | None:
    from app.rules import selectors

    text = body.strip()
    if text:
        text = text[0].upper() + text[1:]
    if text == "Defending player can't cast spells this turn.":
        return (
            [
                {
                    "do": "cast_limit",
                    "who": "defending_player",
                    "until": "turn",
                    "filter": None,
                    "from": None,
                    "act": None,
                }
            ],
            None,
            False,
        )
    if text == "Defending player may draw a card.":
        return (
            [
                {"do": "may_rest", "who": "defending_player", "label": "Draw a card"},
                {"do": "draw", "who": "defending_player", "n": 1},
            ],
            None,
            False,
        )
    if text == "Defending player may have you draw a card. If they do, untap ~ and remove it from combat.":
        return (
            [
                {
                    "do": "may_rest",
                    "who": "defending_player",
                    "label": "Have the attacking creature's controller draw a card",
                },
                {"do": "draw", "who": "you", "n": 1},
                {"do": "untap", "who": "self"},
                {"do": "remove_from_combat", "who": "self"},
            ],
            None,
            False,
        )
    m = re.fullmatch(
        r"Defending player may pay (?P<mana>(?:\{[^}]+\})+)\. If that player (?P<did>does|doesn't), (?P<rest>.+)",
        text,
    )
    if m:
        effects: list[dict[str, Any]] | None = None
        if m["rest"] == "~ can't be blocked this turn.":
            effects = [{"do": "restrict", "who": "self", "rules": ["cant_be_blocked"]}]
        elif m["rest"] == "prevent all combat damage that would be dealt by ~ this turn.":
            effects = [
                {"do": "prevent_all", "scope": {"combat": True, "any_target": True, "by_objects": "self"}}
            ]
        if effects is not None:
            cond: dict[str, Any] = {"succeeded": "defender_pay"}
            if m["did"] == "doesn't":
                cond = {"not": cond}
            return (
                [
                    {
                        "do": "optional_payment",
                        "who": "defending_player",
                        "cost": m["mana"],
                        "bind": "defender_pay",
                    },
                    {"do": "only_if", "cond": cond, "skip": len(effects)},
                    *effects,
                ],
                None,
                False,
            )
    fury = "deals X damage to defending player, where X is the number of cards in their hand."
    if text == f"~ {fury}" or (it == "self" and text == f"It {fury}"):
        return ([{"do": "damage", "who": "defending_player", "n": {"hand": "defending_player"}}], None, False)
    if (
        text
        == "~ gets +X/+0 until end of turn, where X is the number of creature cards in defending player's graveyard."
    ):
        sel = selectors.Selector(types=("Creature",), card=True, zones=("graveyard",), zone_owner=None)
        return (
            [{"do": "pump", "who": "self", "p": {"defending_player_graveyard_count": sel.key()}, "t": 0}],
            None,
            False,
        )
    return None
