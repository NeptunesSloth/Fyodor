"""-- turn watches (wave 7D) -- "Whenever [event] this turn, [effect]" and "When you next cast [spell] this turn,
[effect]": a delayed triggered ability whose trigger event is an ordinary one (CR 603.7, 603.7c). Researched against the
Comprehensive Rules of 2026-09-25.

* 603.7: a resolving spell or ability creates the delayed triggered ability; "whenever" ones trigger every time the event
  happens until the turn ends (cleanup, 514.2; "this turn" is the duration, 611.2a), "when you next cast" ones trigger
  once, for the first matching spell cast after it was created (603.7b).
* The event is a generic trigger condition (app/rules/events.py): what happened after the watch was created, matched
  with the same code the permanents' triggers use (app/rules/triggers.py), against the objects as they were then
  (603.10a). Events of the creating resolution that happened before the watch existed never trigger it (603.7a).
* The watch is the creating ability's: its controller and source are fixed as it was created (603.7d-e). "You" is its
  controller; "another" is relative to its source.
* "that spell" / "that creature" / "that much" / "that player" read what the watch triggered on (603.7c, 608.2k).
* Refused (the sentence stays manual): a watch on its own source or on what it is attached to ("Whenever this creature
  attacks this turn"), "one or more …" and damage events that join several recipients, a target of the deferred ability
  (chosen as it triggers: not modelled), a watch with its own delayed trigger or duration inside.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from app.rules import delayed

if TYPE_CHECKING:
    from app.rules.plan import Plan

_OBJECT_SUBJECTS = {"player", "sel"}  # (not "self", "host": a watch has no object of its own to look at)
_NEXT_CAST_KEYS = {"event", "subject", "player", "spell"}


def cond_ok(cond: dict[str, Any] | None) -> bool:
    """Is this condition one a turn watch can read: an event about players or objects matching a selector, one fact at a
    time (a "one or more" / several-recipients damage event joins facts: not modelled)."""
    if cond is None or cond.get("subject") not in _OBJECT_SUBJECTS or cond.get("aggregate") or cond.get("while"):
        return False
    if cond["event"] in ("multi", "either", "dealt_damage", "you_attack", "unblocked") or cond.get("copy"):
        return False
    return not (cond["event"] == "deal_damage" and cond.get("to", "any") == "any")


def refs_ok(cond: dict[str, Any], effects: list[dict[str, Any]]) -> bool:
    """What the deferred effects name of the event (a spell, a player, an amount, an object) must be there."""
    from app.rules import scripts

    text = json.dumps(effects)
    if any(e.get("who") == "event_spell" for e in effects) and not (cond["event"] == "cast" and cond["subject"] == "player"):
        return False
    wants_player = any(e.get("who") in ("event_player", "each_other_opponent") for e in effects)
    wants_amount = any(scripts._wants_amount(e.get(k)) for e in effects for k in ("n", "p", "t", "mv"))
    if wants_player and not scripts._has_player(cond):
        return False
    if wants_amount and cond["event"] not in scripts._AMOUNT_EVENTS:
        return False
    # (the object the event happened to: only an event about objects has one)
    return not (re.search(r'"(?:ref:)?event(?:\.\w+)?"', text) and cond["subject"] != "sel")


def build(cond: dict[str, Any] | None, clause: str, *, once: bool, text: str) -> tuple[list[dict[str, Any]], Any] | None:
    """The ``delayed`` effect and its deferred effects for "[whenever / when you next …] this turn, <clause>"."""
    from app.rules import scripts

    if not cond_ok(cond) or cond is None:
        return None
    inner = scripts._clause(clause)
    if inner is None or inner[1] is not None:  # (the deferred ability's own target: chosen as it triggers)
        return None
    effects = delayed.inner_for_event(inner[0])
    if effects is None or any(e.get("do") in delayed.UNDEFERRABLE for e in effects) \
            or not refs_ok(cond, effects):
        return None
    head = {"kind": "watch", "cond": cond, "text": text}
    wrapped = delayed.wrap_when(effects, head, this_turn=True)
    wrapped[0]["once"] = once
    return wrapped, None


def deferred_event_effects(effects: list[dict[str, Any]]) -> set[int]:
    """The indices of the effects a watch defers: what they name of "the event" is the watch's own, not the creating
    ability's (scripts._event_refs_ok / _event_spell_ok skip them)."""
    out: set[int] = set()
    for i, e in enumerate(effects):
        if e.get("do") == "delayed" and e.get("when", {}).get("kind") == "watch":
            out.update(range(i + 1, i + 1 + int(e.get("n", 0))))
    return out


def on_facts(plan: Plan, facts: list[Any], batch: int) -> None:
    """One event's facts: the watches created before it that it matches trigger (603.7)."""
    r = plan.rules
    mine = [t for t in r.delayed if t.when.get("kind") == "watch" and (batch < 0 or batch > int(t.when.get("since", 0)))]  # (batch -1: as it happens)
    if not mine:
        return
    from app.rules import triggers

    fired = []
    for t in mine:
        source = plan.state.cards.get(t.source_card or "")
        if source is None or t.controller not in plan.live():
            continue
        watcher = source.model_copy(update={"controller": t.controller})
        for fact in facts:
            if triggers._cond_matches(plan, t.when["cond"], watcher, fact):
                delayed._fire(plan, t, triggers._event(plan, fact, batch))
                if t.once:
                    fired.append(t)
                    break
    if fired:
        r.delayed = [t for t in r.delayed if t not in fired]


# "When you next cast …, copy that spell. You may choose new targets for the copy." — the second sentence belongs to the
# deferred ability (it follows the copy it is about: 707.10c), so the two are read as one clause
_COPY_RETARGET = re.compile(r"(?P<head>\b[Ww]hen you next cast [^.]*? this turn, copy (?:that spell|it)(?: (?:twice|three times|[xX] times))?)"
                            r"\. [Yy]ou may choose new targets for the cop(?:y|ies)\.")


def join_retarget(body: str) -> str:
    return _COPY_RETARGET.sub(lambda m: f"{m['head']} and you may choose new targets for the copy.", body)


def bind_x(value: Any, x: int) -> Any:
    """The creating spell's X (107.3) as a plain number in the deferred effects ("copy that spell X times")."""
    if value == {"x": 1}:
        return x
    if isinstance(value, list):
        return [bind_x(v, x) for v in value]
    if isinstance(value, dict):
        return {k: bind_x(v, x) for k, v in value.items()}
    return value
