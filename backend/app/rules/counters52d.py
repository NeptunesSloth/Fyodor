"""-- counters (wave 52D) -- counter wordings the grammar did not read.

* **As it is turned face up.** 708.11: "As [this permanent] is turned face up, put five +1/+1 counters on it." (Hooded Hydra, Bubble Smuggler) is applied while the
  permanent is being turned face up, not afterwards: the counters are there before any state-based action is checked (a 0/0 Hooded Hydra would die as a trigger
  resolved) and nobody can respond between. They go on through the counter choke point (122.6, as the megamorph counter does, 702.37b).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

_FACE_UP = re.compile(r"^As ~ is turned face up, put (?P<n>an?|one|two|three|four|five|six|seven|eight|nine|ten) (?P<k>\+1/\+1) counters? on it\.$")
_NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
FACE_UP = "turned_up_counters"


def face_up_definition(text: str) -> dict[str, Any] | None:
    m = _FACE_UP.match(text)
    return None if m is None else {"kind": "replacement", "replacement": FACE_UP, "counter": m["k"], "n": _NUMBERS[m["n"]], "effects": []}


def turned_up(plan: Plan, card: CardInstance) -> None:
    """The counters of the "As ~ is turned face up" abilities of a permanent that has just been turned face up (708.11)."""
    from app.rules import replace, scripts

    if plan.manual(card):
        return
    ch = plan.ch(plan.state.cards[card.id])
    for d in scripts.definitions(ch).values():
        if d.get("replacement") == FACE_UP:
            replace.put_counters(plan, [(card.id, d["counter"], d["n"])], by=card.controller)
        elif d.get("face_up110h"):  # -- counters (wave 110H) -- "As ~ enters or is turned face up, put X counters": the entry amount again
            from app.rules import replacements

            if (n := replacements._counter_amount(plan, card.id, card.controller, d, None)) > 0:
                replace.put_counters(plan, [(card.id, d["counter"], n)], by=card.controller)
