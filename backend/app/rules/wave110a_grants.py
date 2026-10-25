"""Wave 110A: spells you cast from hand gain a keyword cost as you cast them (a table alternative cost, like prowl/web-slinging)."""
from __future__ import annotations

import re
from typing import Any

# 702.74a: evoke is an alternative cost; "Elemental permanent spells you cast from your hand gain evoke {4} as you cast them." (Ashling, the Limitless)
_EVOKE = re.compile(r"^(?P<sel>[A-Za-z]+ permanent) spells you cast from your hand gain evoke (?P<cost>(?:\{[^}X]+\})+) as you cast them$")


def grant_evoke(t: str) -> dict[str, Any] | None:
    from app.rules import alt_costs
    from app.rules.permissions import spell_filter

    m = _EVOKE.fullmatch(t)
    if m is None or alt_costs.parse_cost(f"pay {m['cost']}") is None or (key := spell_filter(m["sel"])) is None:
        return None
    return {"kind": "static", "static": "alt_cost", "cost": f"pay {m['cost']}", "table": True, "filter": key, "once": False, "zone": "hand",
            "mv": None, "cond": None, "tag": "evoke", "effects": []}


UMBRA = "Auras attached to permanents you control have umbra armor."


def umbra_static(t: str) -> dict[str, Any] | None:
    """Umbra Mystic: a table static read by ``has_umbra``."""
    return {"kind": "static", "static": "umbra_grant110a", "effects": []} if t == UMBRA else None


def has_umbra(plan: Any, aura: Any, host: Any) -> bool:
    """702.89a: the Aura has umbra armor itself, or an Umbra Mystic-like static gives it to Auras on its controller's permanents."""
    from app.rules import permissions

    if not aura.zone.endswith(":battlefield") or plan.manual(aura):
        return False
    if any(ab.kind == "keywords" and "umbra armor" in ab.keywords for ab in plan.ch(aura).abilities):
        return True
    return "Aura" in plan.ch(aura).subtypes and any(
        src.controller == host.controller for src, _, _ in permissions._table_statics(plan.state, plan.info, {"umbra_grant110a"}))
