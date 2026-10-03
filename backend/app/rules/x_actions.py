"""-- X actions (wave 9A) -- keyword actions whose number is defined by the text: "bolster X, where X is the number of
tapped creatures you control", "amass Orcs X, where X is that spell's mana value", "target creature connives X, where
X is the number of attacking creatures", "it endures X, where X is the number of counters on this creature",
"investigate X times, where X is the number of opponents you have".

107.3c: the text defines X, so the controller doesn't choose it; the value is worked out as the instruction is carried
out (608.2h). Each action is read by its ordinary template with the number 1 (701.39a bolster, 701.47a amass, 701.50d
connive N, 701.63a endure N), and that 1 is then replaced by the value, so the actions keep one grammar. Researched
against CR 2026-09-25. "Investigate X times" is X Clue tokens, as the "investigate for each …" wording already is.
"""

from __future__ import annotations

import re
from typing import Any


def templates(sel: str) -> list[tuple[re.Pattern[str], Any]]:
    head = (rf"bolster|amass [A-Z][a-z]+|(?:~|it|he|she|{sel}) connives|(?:it|~|this creature) endures|investigate")
    return [(re.compile(rf"^(?P<head>{head}) X(?P<times> times)?, where X is (?P<xdef>.+)$"), _build)]


def _build(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import scripts

    head = m["head"]
    if (head == "investigate") != (m["times"] is not None):
        raise scripts._NoMatch  # ("investigate X times"; the others take no "times")
    value = scripts._x_amount(m["xdef"])
    found = scripts._one_clause("investigate" if head == "investigate" else f"{head} 1")
    if found is None:
        raise scripts._NoMatch
    effects, target = found
    if len(effects) != 1 or effects[0].get("n") != 1:
        raise scripts._NoMatch
    return [{**effects[0], "n": value}], target
