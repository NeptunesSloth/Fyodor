"""Bounded compound kicker entry replacements (CR 614.1c, 702.33e)."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.oracle import AbilityText


def parse(ability: AbilityText, text: str) -> dict[str, Any] | None:
    from app.rules import scripts

    # The extra counters are added to intrinsic vanishing, not substituted for it.
    extra = re.fullmatch(r"If ~ was kicked, it enters with (\w+) additional ([a-z]+) counters on it\.", text)
    if extra:
        return scripts.define_replacement(ability, f"If ~ was kicked, it enters with {extra[1]} {extra[2]} counters on it.")
    multi = re.fullmatch(
        r"If ~ was kicked, it enters with (\w+) (\+1/\+1|-1/-1) counters and "
        r"a (trample|flying|haste|vigilance) counter on it and with (haste|flying|trample)\.", text)
    if multi and multi[1] in ("one", "two", "three", "four", "five"):
        n = scripts.num(multi[1])
        return {"kind": "replacement", "replacement": "enters_with_counters", "effects": [],
                "counter": multi[2], "n": n, "also": [{"counter": multi[3], "n": 1, "if_kicked": True}],
                "if_kicked": True, "grant": [multi[4]]}
    discarded = re.fullmatch(
        r"If ~ was kicked, it enters with (flying|trample|haste) and with X "
        r"(\+1/\+1|-1/-1) counters on it, where X is the discarded card's mana value\.", text)
    if discarded:
        return {"kind": "replacement", "replacement": "enters_with_counters", "effects": [],
                "counter": discarded[2], "n": {"entry_discarded_mana_value": True},
                "if_kicked": True, "grant": [discarded[1]]}
    return None
