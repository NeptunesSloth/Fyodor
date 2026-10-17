"""-- cast riders (wave 25C) -- "When you next cast a creature spell this turn, that creature enters with an additional +1/+1 counter on it."
(Kumano Faces Kakkazan, Summon: Fenrir, Long List of the Ents) and "…, it gains haste until end of turn." (Summon: Brynhildr): a turn
watch (app/rules/watches.py, 603.7) whose deferred effect changes the spell it triggered on, researched against CR 2026-09-25.

* 603.7c / 608.2k: the delayed trigger goes on the stack above the creature spell that triggered it, and "that creature" is that spell,
  still on the stack when it resolves; once the spell has resolved (or is gone: countered, a new object, 400.7) the effect does nothing.
* 614.1c: "enters with an additional +1/+1 counter" is a replacement effect of the permanent entering; 613.1f / 611.2a: "gains haste until
  end of turn" is a continuous effect from the moment it enters. Both are riders on the spell's payment record
  (``PaymentRecord.mana_riders``, kinds "counter" and "haste": the same ones mana of a Cavern or a Hall carries, app/rules/mana_units.py,
  106.6), which the entering permanent reads as it enters (``mana_units.entering_counters`` / ``entered``). One rider per counter.
* Only a creature spell: the watch's spell selector must say so ("a creature spell", "a Bird creature spell"), else "that creature" would
  name no creature (the sentence stays manual).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_NUMBERS = {"an": 1, "one": 1, "two": 2, "three": 3}
_COUNTERS = re.compile(r"^(?:that creature|it) enters with (?P<n>an|one|two|three) additional \+1/\+1 counters? on it$", re.IGNORECASE)
_HASTE = re.compile(r"^(?:that creature|it) gains haste until end of turn$", re.IGNORECASE)


def _creature_spell_watch(cond: dict[str, Any] | None) -> bool:
    from app.rules import selectors

    if cond is None or cond.get("event") != "cast" or cond.get("subject") != "player" or cond.get("player") != "you":
        return False
    key = cond.get("spell")
    sel = selectors.from_key(key) if isinstance(key, str) and key.startswith(selectors.PREFIX) else None
    return sel is not None and sel.types == ("Creature",) and not sel.union and not sel.not_types and sel.zones == ("stack",)


def parse(cond: dict[str, Any] | None, clause: str) -> tuple[list[dict[str, Any]], None] | None:
    """The deferred effect of a "when you next cast a creature spell this turn" watch that changes the spell, or None."""
    text = clause.strip().rstrip(".")
    if (m := _COUNTERS.fullmatch(text)) is not None and _creature_spell_watch(cond):
        return [{"do": "spell_rider", "who": "event_spell", "riders": [{"kind": "counter"}] * _NUMBERS[m["n"].lower()]}], None
    if _HASTE.fullmatch(text) is not None and _creature_spell_watch(cond):
        return [{"do": "spell_rider", "who": "event_spell", "riders": [{"kind": "haste", "until": "end_of_turn"}]}], None
    return None


def spell_rider(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The deferred effect: the creature spell the watch triggered on (while it is still that spell on the stack) gets the riders."""
    from app.rules import copying, values

    times = max(0, values.evaluate(plan, ctx, e["n"])) if "n" in e else 1  # (wave 47D: "for each …", "X additional counters": read as the trigger resolves, 608.2h)
    for sid in copying._stack_objects(plan, ctx, e["who"]):
        rec = plan.rules.payments.get(plan.oid(sid))
        if rec is not None:  # (a spell moved onto the stack by hand has no record: nothing to carry the rider)
            rec.mana_riders = [*rec.mana_riders, *({**r, "name": ctx.get("name") or ""} for r in e["riders"] * times)]
    return True


PRIMITIVES = {"spell_rider": spell_rider}
