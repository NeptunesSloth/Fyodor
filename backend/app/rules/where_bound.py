"""-- bounds defined by text (wave 28D) -- "return target creature card with mana value X or less from your graveyard to the battlefield,
where X is the amount of life you gained this turn" (Celestine, Rodolf Duskbringer), "…, where X is the amount of damage this creature
dealt to that player" (Venerable Warsinger), "…, where X is the amount of mana spent to cast this creature" (Astelli Reclaimer).

CR 107.3c: the text defines X, so it is whatever that text makes it, "Note that the value of X may change while that spell or ability is
on the stack"; 603.3d / 601.2c: a triggered ability's targets are chosen as it is put on the stack, and 608.2b checks them again as it
resolves, against X as it is then. So (review 28D):

* a value settled once the ability triggers (the trigger event's amount, the mana spent to cast the source, kicked, mutated, this turn's
  life gained — which only grows while the ability waits: a target chosen under the smaller bound meets the larger) is read as the ability
  is put on the stack: ``bind`` replaces the marker with the number;
* a value that can change while it waits ("the number of Faeries you control": Spellstutter Sprite; Shrines, lands, modified creatures,
  devotion, cards in your hand) stays a marker that ``selectors.matches`` reads each time (``read_live``): as the target is chosen, again
  as it resolves (a Faerie that died meanwhile makes a spell over the new X an illegal target), and for a new target (115.7);
* a value mixing both, or anything else, isn't read: the line stays manual.

A reflexive trigger ("When you do") is put on the stack the next time a player would receive priority (603.12), so its bound is read
then. The selector compares with a marker (``wx:<value>``: the value, encoded); an unbound settled marker matches nothing.
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


# -- review 28D -- 107.3c: which bound values are settled once the ability triggers, which are read again as it resolves (608.2b)
_SETTLED = ({"event_amount", "of"}, {"event_amount"}, {"mana_spent"}, {"turn_history"}, {"kicked"}, {"mutated"})


def _kind(v: Any) -> str | None:
    """"settled", "live", "int" or None (not read) for a bound's value."""
    if isinstance(v, int):
        return "int"
    if not isinstance(v, dict):
        return None
    if set(v) in _SETTLED:
        return "settled"
    if set(v) == {"count"} and isinstance(v["count"], str) and not re.search(r"chosen|event|target|that_player|ref", v["count"]):
        return "live"  # (permanents counted from the controller's view: nothing the trigger event or a target names)
    if set(v) == {"devotion"} or v in ({"hand": "you"}, {"hand": "all"}):
        return "live"
    if set(v) in ({"plus"}, {"times"}):
        parts = v.get("plus") or v.get("times") or []
        kinds = {_kind(x) for x in (parts if isinstance(parts, list) else [parts])} - {"int"}
        return kinds.pop() if len(kinds) == 1 and None not in kinds else None
    return None


def live(value: Any) -> bool:
    return _kind(value) == "live"


def read_live(plan: Plan, mark: str, controller: str, source_card: str | None) -> int | None:
    """A live marker's number now (``selectors.matches``); None for a settled one that wasn't bound (it matches nothing)."""
    try:
        value = json.loads(base64.urlsafe_b64decode(mark[len(MARK):]).decode())
    except ValueError:
        return None
    if not live(value):
        return None
    from app.rules import values

    card = plan.state.cards.get(source_card or "")
    return values.evaluate(plan, {"controller": controller, "source_card": source_card,
                                  "source_object": plan.oid(card) if card is not None else None, "targets": []}, value)


def marker(value: Any) -> str:
    return MARK + base64.urlsafe_b64encode(json.dumps(value, sort_keys=True).encode()).decode()


def tag(found: Any, value: Any, sentinel: int) -> Any:
    """The target (a selector key) or target groups of a sentence parsed with ``sentinel`` for X, with that number in each selector's
    comparisons read as the value (None: it isn't there, or the value can't be read before the targets are chosen)."""
    if not plain(value) or _kind(value) not in ("settled", "live"):
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
    """The ability with each settled marker replaced by the number it stands for now (as the ability is put on the stack); a live one
    stays, read by ``selectors.matches`` each time. Only the ability's own targets: a reflexive ability's ("When you do, … target …")
    is bound when it is put on the stack in turn (603.12; review 28D: life gained in response to the first counts)."""
    own = {k: ability[k] for k in ("target", "targets", "modes") if ability.get(k)}
    if MARK not in json.dumps(own):
        return ability
    from app.rules import values

    ctx: dict[str, Any] = {"controller": controller, "source_card": source_card, "source_object": source_object, "targets": [],
                           "event": event}

    def number(m: re.Match[str]) -> str:
        value = json.loads(base64.urlsafe_b64decode(m.group(1)).decode())
        return m.group(0) if live(value) else str(values.evaluate(plan, ctx, value))

    return {**ability, **json.loads(_MARKED.sub(number, json.dumps(own)))}
