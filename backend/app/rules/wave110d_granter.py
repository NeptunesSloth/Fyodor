"""-- granter counters (wave 110D) -- an ability a static grant gave that names the granting Aura (607.1a, scripts._granter_view).

* Heliod's Punishment: "{T}: Remove a task counter from <Aura>. Then if it has no task counters on it, destroy <Aura>." "it" after "Remove a [kind] counter from
  <granter>" is that same object (608.2c), so it is rewritten to the granter before the grammar reads it.
* Hold for Ransom: "{7}: <Aura>'s controller sacrifices it and draws a card." — the Aura's controller (not the activator) does both; 701.21a: a player can only
  sacrifice a permanent they control, so the creature is sacrificed only if the Aura's controller controls it, and they draw either way.
"""
from __future__ import annotations

import re
from typing import Any

_IT = re.compile(r"(Remove an? (\w+) counter from ‹granter(?:#[^›]*)?›[^.]*\. Then if) it has no \2 counters on it")
_HOLD = re.compile(r"‹granter(?:#[^›]*)?›'s controller sacrifices it and draws a card\.")
HOLD = "hold110d:"


def text(effect: str) -> tuple[str, str]:
    """(the effect in a wording the grammar reads, a marker for ``bound``)."""
    if _HOLD.match(effect.lstrip()):
        return _HOLD.sub("Draw a card.", effect.lstrip(), count=1), HOLD  # (a stand-in the grammar reads: the effects are replaced by ``bound``)
    return _IT.sub(lambda m: f"{m[1]} ‹granter› has no {m[2]} counters on it", effect), ""


def cond(e: dict[str, Any], oid: str) -> dict[str, Any]:
    """A condition about the source's counters reads the granter's (values.py "granter:<object id>")."""
    c = e.get("cond")
    if e.get("do") == "only_if" and isinstance(c, dict) and c.get("value", {}).get("counters") and c["value"].get("on") == "self":
        return {**e, "cond": {**c, "value": {**c["value"], "on": f"granter:{oid}"}}}
    return e


def bound(d: dict[str, Any], oid: str) -> dict[str, Any] | None:
    return {**d, "effects": [{"do": "hold_ransom110d", "oid": oid[len(HOLD):]}]} if oid.startswith(HOLD) else None


def hold(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    aura = plan.state.cards.get(e["oid"].rsplit(".", 1)[0])
    if aura is None or not aura.zone.endswith(":battlefield") or plan.oid(aura) != e["oid"]:
        return True
    me = aura.controller
    host = plan.state.cards.get(ctx.get("source_card") or "")
    if host is not None and host.zone.endswith(":battlefield") and plan.oid(host) == ctx.get("source_object") and host.controller == me:
        effects._sacrifice_cards(plan, [host.id], me, ctx, None)
    return effects.PRIMITIVES["draw"](plan, ctx, {"do": "draw", "who": f"player:{me}", "n": 1})


def untap_each(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """-- Curse of Bounty -- "Each opponent attacking that player does the same" for "untap all nonland permanents you control" (attached_players.does_the_same)."""
    from app.rules import effects

    for p in effects._players(plan, ctx, "attacking_opponents"):
        effects.PRIMITIVES["untap"](plan, ctx, {"do": "untap", "who": e["who"].replace('"controller":"you"', f'"controller":"player:{p}"')})
    return True


PRIMITIVES = {"hold_ransom110d": hold, "untap_each110d": untap_each}
