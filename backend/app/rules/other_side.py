"""The creature on the other side of a trigger event (wave 6D), researched against CR 2026-09-25.

"Whenever this creature blocks or becomes blocked by a creature, destroy that creature." / "Whenever this creature
deals combat damage to a creature, tap that creature …": "that creature" is the creature the event paired this one
with — the attacking creature it blocked (509.3b: once for each), the creature that blocked it (509.3d: once for
each), or the creature it dealt damage to (120.1; one trigger per creature dealt damage). The trigger event
(TriggerEvent.objects) carries that creature, captured as it triggered (603.2, 608.2k); the subject the condition
matched (this creature, "a Warrior you control") is still the watcher's business (app/rules/triggers.py).

Only "that creature" names it: in these abilities a bare "it" before any "that creature" is the source ("it deals 2
damage to that creature", Acolyte of the Inferno), so such an ability stays manual. After "that creature" a pronoun
reads it the ordinary way ("Destroy that creature. It can't be regenerated.", "tap that creature and it doesn't
untap …"). As for any trigger event object, an instruction finds the creature only while it is still that object
(400.7): one that died from the damage is gone (603.10a gives its last known information only).
"""

from __future__ import annotations

import re
from typing import Any

from app.game.rules_state import ObjectRef, TriggerEvent

_THAT = re.compile(r"\bthat (?:creature|permanent)(?:'s)?\b")  # (wave 30S: "becomes unattached from a permanent, sacrifice that permanent")
_IT = re.compile(r"\b(?:it|its|itself)\b", re.IGNORECASE)


def wanted(cond: dict[str, Any] | None) -> bool:
    """A condition whose event pairs this object with a creature on the other side."""
    if not cond:
        return False
    # (-- trigger other (wave 44B) -- "deals combat damage to a planeswalker, destroy that planeswalker": the planeswalker dealt damage, 120.1)
    return bool(cond.get("other")) or (cond.get("event") == "deal_damage" and cond.get("to") in ("creature", "planeswalker"))


def antecedent(cond: dict[str, Any] | None, body: str) -> str | None:
    """"event" (the other creature) when the body names it as "that creature" before any bare pronoun; else None."""
    if not wanted(cond):
        return None
    that, it = _THAT.search(body), _IT.search(body)
    if that is None or (it is not None and it.start() < that.start()):
        return None
    return "event"


def event(plan: Any, info: dict[str, Any], base: TriggerEvent) -> TriggerEvent:
    """The trigger event with the other creature as its object (as it is, or as it last existed: 603.10a)."""
    card, oid = info.get("other"), info.get("other_oid")
    if not card or not oid:
        return base.model_copy(update={"objects": [], "new_objects": []})
    snap = None
    obj = plan.state.cards.get(card)
    if obj is None or plan.oid(obj) != oid:
        snap = plan.rules.lki.get(oid)
    zone = snap.zone if snap is not None else (obj.zone if obj is not None else None)
    return base.model_copy(update={"objects": [ObjectRef(card=card, object_id=oid, zone=zone, snapshot=snap)],
                                   "new_objects": []})
