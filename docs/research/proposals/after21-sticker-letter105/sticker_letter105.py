"""A chosen initial counts name stickers rather than words in the resulting name."""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from unicodedata import category

TEXT = "Whenever ~ attacks, choose a letter. ~ gets +1/+1 until end of turn for each name sticker on it that begins with the chosen letter."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import oracle, scripts

    if oracle.strip_reminders(scripts.self_text(ability.text, ch.name)).strip() != TEXT:
        return None
    d = scripts.define(
        replace(ability, text="Whenever this Vehicle attacks, this Vehicle gets +1/+1 until end of turn."), ch
    )
    assert d is not None
    value = {"sticker_initial105": "ref:letter105"}
    return {
        **d,
        "effects": [
            {"do": "choose_value", "what": "letter", "who": "you", "as": "letter105"},
            {"do": "pump", "who": "self", "p": value, "t": value},
        ],
    }


def count(plan: Any, ctx: dict[str, Any], value: dict[str, Any]) -> int:
    from app.rules import context

    key = value["sticker_initial105"].removeprefix("ref:")
    letter = (context.refs(ctx).get(key) or {}).get("value", "").casefold()
    if not letter:
        return 0
    card = plan.state.cards.get(ctx.get("source_card") or "")
    if card is None or plan.oid(card) != ctx.get("source_object"):
        return 0
    return sum(
        m.sticker.kind == "name"
        and next(
            (c.casefold() for c in m.sticker.text if not c.isspace() and not category(c).startswith("P")), ""
        )
        == letter
        for m in card.stickers101
    )
