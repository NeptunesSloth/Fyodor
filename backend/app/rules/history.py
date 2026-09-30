"""This turn's history, for the conditions that look back in time (CR 608.2i): "if you attacked this
turn" (Raid), "if a creature died this turn" (Morbid), "if a permanent left the battlefield under
your control this turn" (Revolt), "if an opponent lost life this turn", "if you gained 3 or more
life this turn", "if you've drawn two or more cards this turn", "if you lost life last turn".

The facts are recorded deterministically as the game happens (app/game/rules_state.py ``TurnLog``:
``track`` / ``emit`` for what the table shows — departures, life, draws — and the declaration of
attackers, 508.1), so they survive saves, undo / redo and replay. This module only reads them:

* an effect like this "is not taking any actions on those objects", so they needn't still be where
  they were, nor meet the criteria now, as long as they did then (608.2i): a creature that died is
  read as it last existed on the battlefield — its last known information, with the card types the
  layers gave it (an animated land or a crewed Vehicle was a creature) when the rules engine moved
  it, else its printed ones;
* a creature put onto the battlefield attacking was never declared as an attacker, so it never
  "attacked" (508.4) — only ``declare_attackers`` records an attack;
* "dies" is being put into a graveyard from the battlefield (700.4); "leaves the battlefield" is
  moving to any other zone — a token counts (it moves before it ceases to exist, 111.7).
"""

from __future__ import annotations

from typing import Any

from app.game.rules_state import Departure, TurnLog
from app.rules.plan import Plan


def log_for(plan: Plan, last: bool = False) -> TurnLog:
    """This turn's log (or the turn before's); an empty one if nothing was recorded then."""
    rules = plan.rules
    n = plan.state.turn.number
    if last:
        for log in (rules.turn_log, rules.last_turn_log):
            if log is not None and log.turn == n - 1:
                return log
        return TurnLog()
    return rules.turn_log if rules.turn_log.turn == n else TurnLog()


def departed_types(plan: Plan, d: Departure) -> set[str]:
    """What a permanent was as it last existed on the battlefield (608.2i, 700.4)."""
    if d.types is not None:
        return set(d.types)
    snap = plan.rules.lki.get(d.object_id)
    if snap is None:
        return set()
    from app.rules.triggers import _snapshot_card  # (triggers imports the modules that import this one)

    return set(_snapshot_card(plan, snap)[1].types)


def creatures_died(plan: Plan, *, controller: str | None = None, last: bool = False) -> int:
    """How many creatures were put into a graveyard from the battlefield (this turn), optionally only
    those ``controller`` controlled as they died."""
    return sum(1 for d in log_for(plan, last).left
               if d.to == "graveyard" and (controller is None or d.controller == controller)
               and "Creature" in departed_types(plan, d))


def holds(plan: Plan, ctx: dict[str, Any], cond: dict[str, Any]) -> bool:
    """Is this ``{"history": …}`` condition true for the ability's controller right now?"""
    kind = cond["history"]
    me: str = ctx["controller"]
    n = int(cond.get("n", 1))
    log = log_for(plan, bool(cond.get("last")))
    if kind == "attacked":
        return me in log.attacked
    if kind == "gained":
        return log.gained.get(me, 0) >= n
    if kind == "drew":
        return log.drew.get(me, 0) >= n
    if kind == "spells":
        return plan.rules.spells_this_turn(me, plan.state.turn.number) >= n
    if kind == "lost":
        who = cond.get("who", "you")
        players = [me] if who == "you" else [p for p in plan.live() if p != me] if who == "opponent" else list(plan.live())
        return any(log.lost.get(p, 0) >= n for p in players)
    if kind == "left_graveyard":
        return me in log.left_graveyard
    if kind == "died":
        return creatures_died(plan, controller=me if cond.get("who") == "you" else None, last=bool(cond.get("last"))) >= n
    if kind == "left":
        return sum(1 for d in log.left if cond.get("who") != "you" or d.controller == me) >= n
    raise ValueError(f"unknown history condition {cond!r}")
