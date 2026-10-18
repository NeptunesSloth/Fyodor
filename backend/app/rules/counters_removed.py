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


# "Remove all flood counters from this enchantment. If no counters were removed this way, [A]. Otherwise, [B]." (Bounty of the Luxa): 608.2c, 122.8 — the number it actually removed
# decides which of the two is carried out (never both): none removed → A, some removed → B.
_EITHER_WAY = re.compile(r"^(?P<remove>[Rr]emove all [\w+/-]+ counters from [^.]+?)\. If no counters were removed this way, (?P<a>[^.]+)\. Otherwise, (?P<b>[^.]+)\.?$")


def either_way(body: str, read: Any) -> tuple[list[dict[str, Any]], Any, bool] | None:
    m = _EITHER_WAY.match(body.strip())
    if m is None:
        return None
    first, a, b = read(f"{m['remove']}."), read(f"{m['a']}."), read(f"{m['b']}.")
    if not first or not a or not b or len(first[0]) != 1 or first[0][0].get("do") != "remove_counters" or any(x[1] is not None or x[2] for x in (first, a, b)):
        return None
    if any("ref:" in str(x[0]) or "event" in str(x[0]) for x in (a, b)):
        return None  # (a pronoun or a reference to an earlier instruction: not read)
    name = "removed0"
    return [{**first[0][0], "bind": name},
            {"do": "only_if", "cond": {"value": {"ref_amount": name}, "op": "==", "n": 0}, "skip": len(a[0])}, *a[0],
            {"do": "only_if", "cond": {"value": {"ref_amount": name}, "op": ">=", "n": 1}, "skip": len(b[0])}, *b[0]], None, False
