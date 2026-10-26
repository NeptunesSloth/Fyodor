"""-- Voltaic Visionary (wave 110C) -- "When you play a card exiled with this creature, transform this creature."

607.2a: linked to the creature's own exile ability (exiled_with.py records what it exiled and marks that ability); 603.2: it triggers on playing a land or casting a
spell from exile, and the intervening "if" (603.4) asks whether the played card is the very object the creature exiled: playing it makes a new object (400.7), which is
the next incarnation of the card, so only a card played straight from that exile counts."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = "When you play a card exiled with this creature, transform this creature."
KEY = "exiled_with110c"


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != "triggered" or scripts.self_text(ability.text, ch.name).replace("~", "this creature") != TEXT:
        return None
    base = scripts.define(replace(ability, text="Whenever you play a card from exile, transform this creature."), ch)
    return None if base is None else {**base, "if": {KEY: True}}


def holds(plan: Any, ctx: dict[str, Any]) -> bool:
    """Was a card the event is about played straight from the exile the source exiled it to?"""
    exiled = set(plan.rules.exiled_with.get(ctx.get("source_object") or "", []))
    for ref in (ctx.get("event") or {}).get("objects") or []:
        card, _, n = ref["object_id"].rpartition(".")
        if n.isdigit() and f"{card}.{int(n) - 1}" in exiled:
            return True
    return False
