"""-- bounds defined by text (wave 28D) -- "return target creature card with mana value X or less from your graveyard to the battlefield,
where X is the amount of life you gained this turn" (Celestine, Rodolf Duskbringer), "…, where X is the amount of damage this creature
dealt to that player" (Venerable Warsinger), "…, where X is the amount of mana spent to cast this creature" (Astelli Reclaimer).

CR 107.3c: the text defines X, so it is whatever that text makes it; 603.3d / 601.2c: a triggered ability's targets are chosen as it is put
on the stack, so the bound a target must meet is the value then (the trigger event's amount, this turn's life gained, the mana spent to
cast the source), and it doesn't change after (the stack entry keeps the target's bound spec, 608.2b). A reflexive trigger ("When you do")
is put on the stack the next time a player would receive priority (603.12), so its bound is read then.

The selector compares with a marker (``wx:<value>``: the value, encoded) that ``bind`` replaces with the number as the ability is put on
the stack; an unbound marker matches nothing. Only values a trigger can read before its targets exist are accepted.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any

from app.rules.plan import Plan

MARK = "wx:"
# values a triggered ability can evaluate as its targets are chosen (never a target's, "it"'s or a resolution's)
ALLOWED = frozenset({"count", "counters", "on", "devotion", "kicked", "mutated", "hand", "plus", "times", "event_amount", "of",
                     "turn_history", "mana_spent"})
_MARKED = re.compile(r'\\"wx:([A-Za-z0-9_=-]+)\\"')


def plain(v: Any) -> bool:
    """Is this value readable when a trigger's targets are chosen?"""
    if isinstance(v, int):
        return True
    if not isinstance(v, dict) or not set(v) <= ALLOWED:
        return False
    return all(plain(x) for k, x in v.items() if k in ("plus", "times") for x in (x if isinstance(x, list) else [x]))


def marker(value: Any) -> str:
    return MARK + base64.urlsafe_b64encode(json.dumps(value, sort_keys=True).encode()).decode()


def tag(found: Any, value: Any, sentinel: int) -> Any:
    """The target (a selector key) or target groups of a sentence parsed with ``sentinel`` for X, with that number in each selector's
    comparisons read as the value (None: it isn't there, or the value can't be read before the targets are chosen)."""
    if not plain(value) or isinstance(value, int):
        return None
    pattern = re.compile(rf'(?<![\d.-]){sentinel}(?!\d)')
    swapped = [False]

    def one(what: str) -> str:
        out = pattern.sub(lambda _m: json.dumps(marker(value)), what)
        swapped[0] = swapped[0] or out != what
        return out

    if isinstance(found, str):
        out: Any = one(found)
    elif isinstance(found, list):
        out = [{**g, "what": one(g["what"])} if isinstance(g.get("what"), str) else g for g in found]
    else:
        return None
    return out if swapped[0] else None


def has_marker(d: Any) -> bool:
    return MARK in json.dumps(d, default=str)


def bind(plan: Plan, ability: dict[str, Any], controller: str, source_card: str, source_object: str,
         event: dict[str, Any] | None) -> dict[str, Any]:
    """The ability with each marker replaced by the number it stands for now (as the ability is put on the stack)."""
    raw = json.dumps(ability)
    if MARK not in raw:
        return ability
    from app.rules import values

    ctx: dict[str, Any] = {"controller": controller, "source_card": source_card, "source_object": source_object, "targets": [],
                           "event": event}

    def number(m: re.Match[str]) -> str:
        value = json.loads(base64.urlsafe_b64decode(m.group(1)).decode())
        return str(values.evaluate(plan, ctx, value))

    return json.loads(_MARKED.sub(number, raw))
