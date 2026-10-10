"""-- activated sweep (wave 26C) -- "Sweep — Return any number of Plains you control to their owner's hand. Creatures you control get +1/+1
until end of turn for each Plains returned this way." (Charge Across the Arabian Desert, Plow Through Reito, Sink into Takenuma, Barrel
Down Sokenzan).

CR 2026-09-25: 107.1c any number (including none) is chosen as the spell resolves (608.2d); 608.2c what the next sentences count is what the
first one actually did. effects.return_any returns the chosen lands and keeps their number as the resolution's X, so the sentences that count
them are read as the X they are (an X the grammar already reads); a form not listed here keeps the spell manual."""

from __future__ import annotations

import re

LANDS = {"Plains": "Plains", "Islands": "Island", "Swamps": "Swamp", "Mountains": "Mountain", "Forests": "Forest"}
FIRST = re.compile(rf"(?:^|(?<=\. ))Return any number of (?:{'|'.join(LANDS)}) you control to their owner's hand\.")
_LAND = rf"(?:{'|'.join(LANDS)}|{'|'.join(LANDS.values())})"


def rewrite(body: str) -> str | None:
    """``body`` with the counts of the returned lands written as X; unchanged when it has no such first sentence; None when it
    counts them in a form not read."""
    if FIRST.search(body) is None:
        return body
    out = re.sub(rf"([+-])1/([+-])1 until end of turn for each {_LAND} returned this way", r"\1X/\2X until end of turn", body)
    out = re.sub(rf"\ba card for each {_LAND} returned this way", "X cards", out)
    out = re.sub(rf"\bequal to twice the number of {_LAND} returned this way", "equal to twice X", out)
    return None if "returned this way" in out else out
