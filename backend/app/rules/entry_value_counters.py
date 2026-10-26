"""Entry counter amounts and their bound pre-entry choices."""
from __future__ import annotations

from typing import Any


def parse(text: str) -> dict[str, Any] | None:
    from app.rules import language, selectors

    base: dict[str, Any] = {"kind": "replacement", "replacement": "enters_with_counters", "effects": []}
    if text == "~ enters with a +1/+1 counter on it plus an additional +1/+1 counter on it for each other creature you control.":
        sel = selectors.parse("other creatures you control")
        assert sel is not None
        return {**base, "counter": "+1/+1", "n": {"plus": [1, {"count": sel.key()}]}}
    if text == "If ~ was cast using web-slinging, ~ enters with X +1/+1 counters on ~, where X is the mana value of the returned creature.":
        return {**base, "counter": "+1/+1", "n": {"entry_returned_mv110c": True}}  # (-- web-slinging (wave 110C) -- Scarlet Spider; replacements._counter_amount)
    if text == "~ enters with a number of +1/+1 counters on it equal to the greatest number of cards an opponent has drawn this turn.":
        return {**base, "counter": "+1/+1", "n": {"turn_history": "opp_drew_max"}}
    if text == "~ enters with a number of stun counters on it equal to three minus X. If X is 2 or less, it enters tapped.":
        return {**base, "counter": "stun", "n": {"minus": [3, {"x": 1}]}, "tapped_x_max": 2}
    if text == "~ enters with a +1/+1 counter on it for each instant and sorcery card exiled with it.":
        return {**base, "counter": "+1/+1", "n": {"entry_delved_spells": True}}
    if text == "As ~ enters, choose an opponent. ~ enters with a -1/-1 counter on it for each creature that player controls.":
        choice = language.enters_choice("As ~ enters, choose an opponent.")
        assert choice is not None
        return {**choice, "counters_choice": "opponent",
                "counters": {"counter": "-1/-1", "n": {"entry_opponent_creatures": True}}}
    if text == "~ enters with X +1/+1 counters on it. If X is 5 or more, it enters with an additional X +1/+1 counters on it.":
        return {**base, "counter": "+1/+1", "n": {"entry_x_doubled_at": 5}}
    if text == "If you control five or more untapped lands, ~ enters with two +1/+1 counters and a lifelink counter on it.":
        from app.rules import conditions

        condition = conditions.parse("you control five or more untapped lands")
        if condition is None:
            return None
        return {**base, "counter": "+1/+1", "n": 2, "entry_condition": condition,
                "also": [{"counter": "lifelink", "n": 1, "entry_condition": condition}]}
    return None
