"""-- event batches (wave 28D) -- "this way" in a triggered ability whose event is a batch ("Whenever one or more nonland cards are
milled, put a +1/+1 counter on each of up to X target creatures, where X is the number of nonland cards milled this way": The Wise
Mothman).

CR 603.2c: "one or more" triggers once for everything that happened at the same time, and "this way" in such an ability is that
event's objects (701.17a: cards put into a graveyard from a library are milled). Its targets are chosen as the ability is put on the
stack (603.3d), when the batch is complete, so the number of targets is that batch's size: the trigger event's amount (one per
card that matched the condition). The count names the same cards the condition does (the same selector) or nothing is read.
"""

from __future__ import annotations

import json
from typing import Any

# the trigger condition's event → the verb a "… this way" count names
_VERBS = {"mill": "milled", "discard": "discarded", "sacrifice": "sacrificed"}


def bind(d: dict[str, Any] | None) -> dict[str, Any] | None:
    """The definition with each "number of … <verb> this way" in a target count read as the batch's amount, if the ability is
    triggered by a batch of that verb and the count's qualifier is the condition's own; else it is left for ``this_way.unbound``."""
    if d is None or d.get("kind") != "triggered" or '"this_way"' not in json.dumps(d, default=str):
        return d
    cond = d.get("cond") or {}
    verb = _VERBS.get(cond.get("event"))
    if verb is None or not cond.get("aggregate"):
        return d
    obj = cond.get("obj")
    obj_key = obj if isinstance(obj, str) else (obj.key() if hasattr(obj, "key") else None)

    def swap(v: Any) -> Any:
        if isinstance(v, list):
            return [swap(x) for x in v]
        if isinstance(v, dict):
            if v.get("this_way") == verb and "ref_count" not in v and v.get("of") == obj_key:
                return {"event_amount": 1}
            return {k: swap(x) for k, x in v.items()}
        return v

    return {**d, "targets": swap(d["targets"])} if d.get("targets") else d
