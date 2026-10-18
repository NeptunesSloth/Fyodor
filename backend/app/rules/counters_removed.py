"""-- if you do (wave 52A) -- "Remove all charge counters from this artifact. Add {C} for each charge counter removed this way." (Ventifact Bottle), "… Add one mana of any color for each
charge counter removed this way." (Coalition Relic).

CR 2026-09-25: 122.8 / 608.2c: the counters an earlier instruction of the same ability actually removed (all of one kind from the object, or fewer when it had fewer); 106.3: the
mana is added by the ability as it resolves; "one mana of any color" is chosen for each one on its own (106.1b).
"""

from __future__ import annotations

import re
from typing import Any

_MANA = re.compile(r"^add (?:\{(?P<sym>[WUBRGC])\}|one mana of any color) for each (?P<kind>[\w+/-]+) counters? removed this way$")


def parse(text: str, effects: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """The mana instruction (the removal before it is marked to record how many it removed), or None (not this form)."""
    m = _MANA.match(text)
    if m is None or not effects or effects[-1].get("do") != "remove_counters" or effects[-1].get("kind") != m["kind"] or effects[-1].get("bind"):
        return None
    name = f"removed{len(effects) - 1}"
    effects[-1] = {**effects[-1], "bind": name}
    n = {"ref_amount": name}
    return [{"do": "add_mana", "sym": m["sym"], "n": n} if m["sym"] else {"do": "add_mana", "of": list("WUBRG"), "n": n}]
