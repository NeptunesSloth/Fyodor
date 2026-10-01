"""-- counters & designations (wave 3E) -- Player counters with rules of their own and the
designations a player can have.

* Rad counters (CR 728.1): an inherent triggered ability with no source, controlled by the active
  player — "At the beginning of each player's precombat main phase, if that player has one or more
  rad counters, that player mills a number of cards equal to the number of rad counters they have.
  For each nonland card milled this way, that player loses 1 life and removes one rad counter from
  themselves." The intervening "if" is checked as it triggers and again as it resolves (603.4).

Everything here is deterministic: choices are decisions addressed to the player who makes them.
"""

from __future__ import annotations

from typing import Any

from app.game.state import zone_key
from app.rules.plan import Plan

Context = dict[str, Any]

def status(plan: Plan, you: str, kind: str) -> bool:
    """Conditions about designations (app/rules/conditions.py ``{"status": kind}``)."""
    table = plan.state.table
    monarch = table.monarch if table.monarch in plan.live() else None
    if kind == "no_monarch":  # 725.1: "if there is no monarch"
        return monarch is None
    if kind == "opponent_monarch":
        return monarch is not None and monarch != you
    if kind == "not_monarch":
        return monarch != you
    if kind == "not_initiative":
        return table.initiative != you
    if kind == "completed_dungeon":  # 309.7
        r = plan.state.rules
        return bool(r is not None and r.completed_dungeons.get(you))
    if kind in ("day", "night"):  # 731.1
        return table.day_night == kind
    if kind == "neither_day_nor_night":
        return table.day_night is None
    return False


# -- rad counters (728) -----------------------------------------------------------------------------
RAD_TRIGGER = {"kind": "triggered", "trigger": "rad", "effects": [{"do": "rad"}], "optional": False, "target": None}


def rad_trigger(plan: Plan) -> None:
    """728.1: at the beginning of the active player's precombat main phase (505.1a: the first main
    phase), if they have one or more rad counters."""
    from app.rules import triggers  # (triggers imports the effects that import this module)

    ap = plan.active
    if ap in plan.live() and plan.state.players[ap].resources.get("rad", 0) > 0:
        triggers._add(plan, controller=ap, source_card="", source_object="", name="Rad counters", index=0,
                      definition=RAD_TRIGGER)


def rad(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """728.1 as it resolves: the player (the ability's controller: the active player, whose phase it
    is) mills as many cards as they have rad counters; for each nonland card milled this way, they
    lose 1 life and remove one rad counter."""
    pid = ctx["controller"]
    n = plan.state.players[pid].resources.get("rad", 0) if pid in plan.live() else 0
    if n <= 0:
        return True  # 603.4: no rad counters any more — the ability does nothing
    library = plan.state.zones.get(zone_key(pid, "library"), [])
    milled = list(library[:n])
    if not milled:
        return True
    plan.do({"type": "mill", "player": pid, "count": len(milled)}, actor=pid)
    nonland = sum(1 for cid in milled if cid in plan.state.cards and plan.state.cards[cid].zone == zone_key(pid, "graveyard")
                  and not plan.ch(plan.state.cards[cid]).is_land)
    if nonland:
        plan.do({"type": "life", "player": pid, "delta": -nonland}, actor=pid)  # (728.1a: life lost "from radiation")
        plan.do({"type": "resource", "player": pid, "key": "rad", "delta": -min(nonland, n)}, actor=pid)
    return True


PRIMITIVES: dict[str, Any] = {"rad": rad}
RESUME: dict[str, Any] = {}
