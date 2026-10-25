"""Name-sticker counts use physical name markers, including each letter occurrence."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

TRES = "{3}{U}: ~ gets +1/+0 until end of turn for each name sticker on it. It can't be blocked this turn."
BALLS = "Whenever you put a sticker on ~, it deals damage equal to the number of o's in name stickers on ~ to any target."
SPLASH = "Whenever you put a sticker on ~, tap up to X target creatures, where X is the number of u's in name stickers on ~."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import oracle, scripts

    text = oracle.strip_reminders(scripts.self_text(ability.text, ch.name)).strip()
    if text == TRES:
        d = scripts.define(
            replace(
                ability,
                text="{3}{U}: This creature gets +1/+0 until end of turn. It can't be blocked this turn.",
            ),
            ch,
        )
        assert d is not None
        return {
            **d,
            "effects": [{**d["effects"][0], "p": {"sticker_name_count104": "stickers"}}, *d["effects"][1:]],
        }
    if text not in (BALLS, SPLASH):
        return None
    shell = (
        "Whenever you gain life, this enchantment deals 1 damage to any target."
        if text == BALLS
        else "Whenever you gain life, tap up to two target creatures."
    )
    d = scripts.define(replace(ability, text=shell), ch)
    assert d is not None
    cond = {"event": "put_sticker103", "subject": "self", "sticker_actor104": True}
    if text == BALLS:
        return {**d, "cond": cond, "effects": [{**d["effects"][0], "n": {"sticker_name_count104": "o"}}]}
    return {
        **d,
        "cond": cond,
        "targets": [{**d["targets"][0], "x_count": "upto", "x_value": {"sticker_name_count104": "u"}}],
    }


def count(plan: Any, ctx: dict[str, Any], value: dict[str, Any]) -> int:
    card = plan.state.cards.get(ctx.get("source_card") or "")
    if card is not None and plan.oid(card) == ctx.get("source_object"):
        markers = [m.model_dump() for m in card.stickers101]
    else:
        snap = plan.rules.lki.get(ctx.get("source_object") or "")
        markers = snap.stickers101 if snap is not None else []
    names = [m["sticker"]["text"] for m in markers if m["sticker"]["kind"] == "name"]
    mode = value["sticker_name_count104"]
    return len(names) if mode == "stickers" else sum(n.casefold().count(mode) for n in names)
