"""-- wave 110A -- Karn Liberated: "Restart the game, leaving in exile all non-Aura permanent cards exiled with Karn. Then put those cards onto the
battlefield under your control."

727.1: the game ends (nobody wins, loses or draws) and the players still in it begin a new game by 103; 727.1a: the ability's controller starts.
727.2: every card comes back to its owner's deck. 727.5 / 727.5a: the kept cards are not in their owner's deck, and a kept commander stays its
deck's commander. 727.4: the ability finishes resolving just before the first turn's untap step, once the mulligans (and opening-hand actions)
are done: the kept cards enter then (``opening_hand.finish``; no pregame at the table: at once). Rulings 2020-08-07: the permanents have been under
their controller's control since the beginning of the first turn (they can attack and use {T} abilities); the commander tax, commander casts,
commander damage, life totals, counters and emblems reset; a player who left the game is not in the new game.

The game-level work is one table step (``restart_game`` with ``first`` and ``keep``, app/game/handlers/solo.py); this module picks the kept cards,
runs it and enters them. Not modelled: 727.3 (a library under seven cards loses at the first upkeep: the normal empty-library rule covers it)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import ControlMark

if TYPE_CHECKING:
    from app.rules.plan import Plan

LINE = ("−14: Restart the game, leaving in exile all non-Aura permanent cards exiled with Karn. "
        "Then put those cards onto the battlefield under your control.")
PERMANENT = {"Artifact", "Creature", "Enchantment", "Land", "Planeswalker", "Battle"}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    if ability.text != LINE:
        return None
    from app.rules import exiled_with

    return exiled_with.link({"kind": "activated", "loyalty": True, "cost": "−14", "effects": [{"do": "restart110a", "who": exiled_with.WHO}], "target": None}, ability, ch)


def restart(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import exiled_with

    keep = []
    for cid in exiled_with.cards(plan, ctx, e["who"]):  # still the objects exiled by Karn's first two abilities (607.2a)
        ch = plan.ch(plan.state.cards[cid])
        if PERMANENT & set(ch.types) and "Aura" not in ch.subtypes and plan.state.cards[cid].owner in plan.live():
            keep.append(cid)
    plan.note(f"{ctx['name']}: the game restarts; {len(keep)} card(s) stay in exile", actor=ctx["controller"])
    plan.do({"type": "restart_game", "draw": 7, "first": ctx["controller"], "keep": keep}, actor=ctx["controller"])
    plan.rules.restart_hold110a = True
    plan.rules.stack.clear()  # (the resolving ability went with the old game; finish() copes with its absence)
    if plan.state.pregame is None:  # no mulligan process at this table: the new game begins at once
        enter(plan)
    return True


def enter(plan: Plan) -> bool:
    """727.4: put the kept cards onto the battlefield under the starting player's control. False while an entry choice is pending
    (the rest of ``opening_hand.finish`` then runs from ``THEN``)."""
    from app.rules import attachments

    rec, plan.rules.restart110a = plan.rules.restart110a, None
    if not rec:
        return True
    pid = rec["controller"]
    ids = [c for c in rec["cards"] if c in plan.state.cards and plan.state.cards[c].zone.endswith(":exile")]
    entries = [{"card": c, "player": pid, "actor": pid, "tapped": False} for c in ids]
    ctx: dict[str, Any] = {"controller": pid, "source_card": None, "source_object": None, "name": "Karn Liberated", "effects": [], "next": 0, "x": None,
                           "event": None, "body_done": {"do": "restart_go110a", "cards": ids, "pid": pid}}
    if entries and not attachments.enter(plan, entries, ctx):
        return False
    unsick(plan, ids, pid)
    return True


def unsick(plan: Plan, ids: list[str], pid: str) -> None:
    """Under the starting player's control continuously since the beginning of their first turn (ruling 2020-08-07)."""
    for c in ids:
        if c in plan.state.cards and plan.state.cards[c].zone.endswith(":battlefield"):
            plan.rules.controlled_since[c] = ControlMark(controller=pid, turn=0, changed=False)


def _go(plan: Plan, then: dict[str, Any]) -> None:
    from app.rules import opening_hand

    unsick(plan, then["cards"], then["pid"])
    if plan.state.pregame is not None:
        opening_hand.finish(plan)


PRIMITIVES = {"restart110a": restart}


from app.rules import replace as _replace  # noqa: E402

_replace.THEN["restart_go110a"] = _go
