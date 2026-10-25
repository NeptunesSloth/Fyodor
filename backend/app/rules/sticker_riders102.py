"""Self-entry sticker receipts count the newly placed sticker, never the object's whole name."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

_PREFIX = "When ~ enters, you may put a name sticker on it. "
_GOBLIN = _PREFIX + "Add {R} for each unique vowel on that sticker."
_SAURUS = _PREFIX + "Put a +1/+1 counter on it for each unique vowel on that sticker."
_BIRD = _PREFIX + "You gain X life, where X is the number of unique vowels on that sticker."
_WIZARDS = "When ~ enters, you may put a name sticker on it, then look at the top X cards of your library, where X is the number of unique vowels on that sticker. Put one of those cards into your hand and the rest on the bottom of your library in any order."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import oracle, scripts

    text = oracle.strip_reminders(scripts.self_text(ability.text, ch.name)).strip()
    if text not in (_GOBLIN, _SAURUS, _BIRD, _WIZARDS):
        return None
    native = scripts.define(replace(ability, text="When this creature enters, draw a card."), ch)
    assert native is not None
    receipt = "name102"
    n = {"sticker_vowels102": "ref:" + receipt}
    first = {"do": "put_sticker101", "who": "self", "kind": "name", "n": 1, "as": receipt}
    if text == _GOBLIN:
        tail = [{"do": "add_mana", "sym": "R", "n": n}]
    elif text == _SAURUS:
        tail = [{"do": "add_counters", "who": "self", "kind": "+1/+1", "n": n}]
    elif text == _BIRD:
        tail = [{"do": "gain_life", "who": "you", "n": n}]
    else:
        base = scripts.parse_effects(
            "Look at the top X cards of your library. Put one of those cards into your hand and the rest on the bottom of your library in any order."
        )
        assert base is not None and base[0][0]["do"] == "look_top"
        tail = [{**base[0][0], "n": n}, *base[0][1:]]
    return {**native, "effects": [first, *tail], "optional": False}


def vowels(ctx: dict[str, Any], value: dict[str, Any]) -> int:
    key = value["sticker_vowels102"].removeprefix("ref:")
    records = (ctx.get("sticker_receipts101") or {}).get(key) or []
    return len(set(records[-1]["sticker"]["text"].casefold()) & set("aeiouy")) if records else 0
