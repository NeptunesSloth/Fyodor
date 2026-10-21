"""CR 608.2h / 402.3: draw positive shortfalls from public hand counts or actual discards."""

from __future__ import annotations

import re
from typing import Any


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import this_way, values

    if re.fullmatch(r"If target opponent has more cards in hand than you, draw cards equal to the difference\.?", body, re.IGNORECASE):
        # Drawing zero when the condition is false is equivalent to doing nothing.
        return [{"do": "draw", "who": "you", "n": {"minus": [{"hand": "target"}, {"hand": "you"}]}}], "opponent", False
    if re.fullmatch(r"Each player with fewer cards in hand than the player with the most cards in hand draws cards equal to the difference\.?", body, re.IGNORECASE):
        return [{"do": "draw", "who": "each_player", "n": {"each_hand_shortfall": True}}], None, False
    m = re.fullmatch(r"Target (?P<who>opponent|player) discards (?P<n>two|three|four|\d+) cards\. If fewer than (?P=n) cards were discarded this way, you draw cards equal to the difference\.?", body, re.IGNORECASE)
    if m is not None:
        word = m["n"].lower()
        n = int(word) if word.isdigit() else values.NUMBERS[word]
        # 701.9 / 608.2h: count actual discards, including those whose destination
        # was replaced. Never infer this count from the final graveyard size.
        count = this_way.parse("cards discarded this way")
        assert count is not None
        binding = "shortfall_discard"
        return [{"do": "discard", "who": "target", "n": n, "as": binding},
                {"do": "draw", "who": "you", "n": {"minus": [n, {**count, "ref_count": binding}]}}], m["who"].lower(), False
    return None
