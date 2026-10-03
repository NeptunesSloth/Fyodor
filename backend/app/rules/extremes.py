"""Superlative conditions (wave 8B): "if you control the creature with the greatest power or tied for the
greatest power", "if you control a creature with the greatest power among creatures on the battlefield".

Both read: some object of that kind that you control has a value of the stat that no object of that kind on
the battlefield (any controller) beats. "Tied for the greatest" is what makes a tie count (the "a creature with
the greatest power among" form is the same: any creature holding the greatest value). Without "or tied" the
wording says "the creature", which a tie leaves with no one: refused (stays manual) rather than guessed.
Judged as the condition is checked (603.4: an intervening "if" is checked when the trigger event happens and
again as it resolves; 608.2c for an instruction's own "if"), from the objects' current characteristics
(power/toughness as the layers give them, 613; mana value, 202.3).

``{"extreme": {"stat": "power" | "toughness" | "mana_value", "sel": <selector key of the kind>}}``
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.rules import selectors, values

if TYPE_CHECKING:
    from app.rules.plan import Plan

_STATS = {"power": "power", "toughness": "toughness", "mana value": "mana_value"}
_STAT = "power|toughness|mana value"
_THE = re.compile(rf"you control the (?P<kind>[a-z]+) with the greatest (?P<s>{_STAT}) or tied for the greatest (?P<s2>{_STAT})")
_A = re.compile(rf"you control an? (?P<kind>[a-z]+) with the greatest (?P<s>{_STAT}) among (?P<kinds>[a-z]+) on the battlefield")


def parse(t: str) -> dict[str, Any] | None:
    m = _THE.fullmatch(t)
    if m and m["s"] == m["s2"]:
        kind = m["kind"]
    else:
        m = _A.fullmatch(t)
        if not m or m["kinds"] != m["kind"] + "s":
            return None
        kind = m["kind"]
    sel, plural = selectors.parse(kind), selectors.parse(kind + "s")
    if sel is None or plural is None or sel.key() != plural.key() or sel.player is not None or sel.card:
        return None
    return {"extreme": {"stat": _STATS[m["s"]], "sel": sel.key()}}


def holds(plan: Plan, ctx: dict[str, Any], cond: dict[str, Any]) -> bool:
    spec = cond["extreme"]
    found = selectors.candidates(plan, selectors.from_key(spec["sel"]), ctx["controller"], ctx.get("source_card"))
    stats = [(plan.state.cards[c].controller, values._stat_of(plan.ch(plan.state.cards[c]), spec["stat"])) for c in found]
    known = [s for _, s in stats if s is not None]
    mine = [s for who, s in stats if who == ctx["controller"] and s is not None]
    return bool(mine) and max(mine) >= max(known)
