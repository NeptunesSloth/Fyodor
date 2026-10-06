"""Two creatures chosen up front, then made to fight (CR 701.14, 115.1, 601.2c).

    Choose target creature you control and target creature you don't control. [A rider on the creature you control.]
    Then those creatures fight each other.     (Tail Swipe, Joust, Blizzard Brawl, Malamet Battle Glyph, Hog-Monkey Rampage, …)

The sentences are the same instructions as "[rider on] target creature you control. Then that creature fights target creature you
don't control." (both creatures are targets chosen as the spell is cast, 115.1; the fight happens as it resolves, 701.14a, and does
nothing if either isn't a creature on the battlefield any more, 701.14b): rewritten into two "Choose target …" sentences — the creature
you control last, so "that creature" in the rider names it — and a private fight sentence that ``language._target_forms`` reads as the
fight of the first target group with the second. The rewrite is the only way to that sentence, so it always has exactly those two groups.
"""

from __future__ import annotations

import re

FIGHT = "the two chosen creatures fight each other"  # (never Oracle wording)
_PAIR = re.compile(r"(?P<lead>^|\. |— )Choose target creature you control and target creature (?P<o>you don't control|an opponent controls)\. "
                   r"(?P<mid>.*?)Then (?:those|the chosen) creatures fight each other\.")
_MINE = re.compile(r"\b([Tt])he (?:chosen )?creature you control\b")


def rewrite(body: str) -> str:
    def swap(m: re.Match[str]) -> str:
        mid = m["mid"]
        if re.search(r"\bthe (?:chosen )?creature (?:you don't control|an opponent controls)\b", mid):
            return m[0]  # (a rider on the other creature: not read)
        mid = _MINE.sub(lambda x: f"{x[1]}hat creature", mid)
        return f"{m['lead']}Choose target creature {m['o']}. Choose target creature you control. {mid}Then {FIGHT}."

    return _PAIR.sub(swap, body)
