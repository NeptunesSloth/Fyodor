"""-- activated sweep (wave 26C) -- "Remove all oil counters from this artifact: …" and the number it removed.

CR 2026-09-25: 602.2b -> 601.2h: the cost is paid as the ability is activated, so "all" is every counter of that kind the source has
then; 107.3 / 608.2h: the effect reads that number as it resolves ("the number of oil counters removed this way", "that much", X). The
engine sets the ability's X to that number as it is activated (casting.activate_to_stack) and the cost part removes X counters
(cost_payment), so the sentences that name the removed counters are read as the X they are (an X the grammar already reads); a
sentence whose reference isn't one of the forms below keeps the ability manual.
"""

from __future__ import annotations

import re

from app.rules.costs import AbilityCost

WHERE = re.compile(r",? where X is the number of (?:[\w+/\-]+ )?counters removed this way")


def rewrite(body: str, cost: AbilityCost) -> str | None:
    """``body`` with the removed counters named as X, unchanged when it names none, None when it names them in a form not read."""
    if "removed this way" not in body and "that much" not in body:
        return body
    every = next((c for c in cost.components if c.every), None)
    if every is None:
        return body
    k = re.escape(every.counter or "")
    out = WHERE.sub("", body)
    out = re.sub(rf"\bequal to the number of {k} counters removed this way", "equal to X", out)
    out = re.sub(rf"\b(gets? [+-])1/([+-])1 until end of turn for each {k} counter removed this way", r"\1X/\2X until end of turn", out)
    out = re.sub(rf"\bgain 1 life for each {k} counter removed this way", "gain X life", out)
    out = re.sub(rf"\bgain 2 life for each {k} counter removed this way", "gain twice X life", out)
    out = re.sub(r"\bdeals that much damage\b", "deals X damage", out)
    if "removed this way" in out or "that much" in out:
        return None
    return out
