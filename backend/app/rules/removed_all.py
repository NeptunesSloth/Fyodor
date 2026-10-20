"""Counter-removal costs and references to the amount paid (CR 2026-09-25).

CR 602.2b -> 601.2b/h: a variable cost is announced and paid in full before resolution.
“All” uses every source counter of that kind; “any number” permits zero (107.1c), while
“one or more” has a minimum of one (118.3). The existing announced X carries the amount,
so later references read the payment rather than the source's current counters (608.2h).
Only one counter variable and recognized references are read; unknown references remain manual.
"""

from __future__ import annotations

import re

from app.rules.costs import REMOVE_COUNTER, AbilityCost

WHERE = re.compile(r",? where X is the number of (?:[\w+/\-]+ )?counters removed this way")


def rewrite(body: str, cost: AbilityCost) -> str | None:
    """``body`` with the removed counters named as X, unchanged when it names none, None when it names them in a form not read."""
    per_removed = re.fullmatch(r"For each counter removed, ~ gets \+2/\+0 until end of turn\.", body.strip())
    if "removed this way" not in body and "that much" not in body and "that many" not in body and per_removed is None:
        return body
    removed = [c for c in cost.components if c.kind == REMOVE_COUNTER and c.x]
    if len(removed) != 1:
        return body
    counter = removed[0]
    if per_removed is not None:
        if sum(c.kind == REMOVE_COUNTER for c in cost.components) != 1:
            return None
        return body.replace("For each counter removed,", "For each counter paid,")
    k = re.escape(counter.counter or "")
    out = re.sub(r"(?i)for each five counters removed this way", "For each five counters paid", body)
    out = re.sub(rf",? where X is the number of (?:{k} )?counters removed this way", "", out)
    out = re.sub(rf"\bequal to the number of {k} counters removed this way", "equal to X", out)
    out = re.sub(rf"\b(gets? [+-])1/([+-])1 until end of turn for each {k} counter removed this way", r"\1X/\2X until end of turn", out)
    out = re.sub(rf"\bgain 1 life for each {k} counter removed this way", "gain X life", out)
    out = re.sub(rf"\bgain 2 life for each {k} counter removed this way", "gain twice X life", out)
    out = re.sub(r"\bdeals that much damage\b", "deals X damage", out)
    out = re.sub(r"^(\s*)[Cc]reate that many ", r"\1Create X ", out)
    out = re.sub(r"with (power|toughness|mana value) less than or equal to X\b", r"with \1 X or less", out)
    if "removed this way" in out or "that much" in out:
        return None
    return out
