"""-- declaration choosers (wave 110A) -- "You choose which creatures attack this turn." / "You choose which creatures block this turn [combat]
and how those creatures block." (Master Warcraft, Melee, Odric, Master Tactician).

508.1a / 509.1a: the active (defending) player chooses the attackers (blockers); the effect makes its controller choose instead. Only the choice
moves (the decision's ``decider``, as with Opposition Agent): the objects, their controllers, the legality of the declaration (508.1, 509.1:
requirements and restrictions still bind) and any cost the declaration has stay with the declaring player. The chooser is told nothing hidden
about that player (``Decision.blind``: this is not 723.4 control). It lasts until end of turn, or of combat; a later effect overwrites an earlier one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def chooser(plan: Plan, kind: str, player: str) -> str | None:
    """Who declares ``player``'s attackers/blockers instead of them now (None: they do)."""
    if kind == "block" and (ap := plan.state.turn.active_player) != player and ap in plan.live():  # Invasion Plans (static)
        from app.rules import permissions

        if permissions._table_statics(plan.state, plan.info, {"block_chooser110a"}):
            return ap
    c = plan.rules.declare_choosers.get(kind)
    if c is None or c["turn"] != plan.state.turn.number or c["player"] == player or c["player"] not in plan.live():
        return None
    return str(c["player"])


def declare_chooser(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    plan.rules.declare_choosers[e["kind"]] = {"player": ctx["controller"], "turn": plan.state.turn.number, "combat": bool(e.get("combat"))}
    return True


PRIMITIVES = {"declare_chooser110a": declare_chooser}
