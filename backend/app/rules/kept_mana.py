"""Mana that doesn't empty from a pool (wave 3R3), researched against CR 2026-09-25.

500.4: "When a step or phase ends, any unused mana left in a player's mana pool empties." 106.4: an
effect can let a player keep mana: "Until end of turn, you don't lose this mana as steps and
phases end." (Savage Ventmaw, Su-Chi Cave Guard) or "Until end of combat, you don't lose this mana
as steps end." (Avatar Roku). The engine records the mana the effect just added (``keep``) and
leaves that much in the pool when it empties (:func:`empty`), until the effect ends: "until end of
turn" in the cleanup step (514.2), so the mana empties as the cleanup step ends; "until end of
combat" as the end of combat step ends (511.3).

The pool itself stays one plain count per type (``Player.mana``). The kept amount of a type is
never more than the pool holds (:func:`clamp`, run whenever a pool shrinks): spending uses the
other mana of that type first, the choice a player would make (106.4 lets the player choose which
mana to spend; this is the auto-payer's choice, and kept mana is never worse to keep).

Refused (the card stays manual): kept mana with a spending restriction (Klauth, Karn, Legacy
Reforged: the pool doesn't carry restrictions), "Players don't lose unspent mana" statics
(Upwelling), and amounts the grammar doesn't read.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.state import COMBAT_PHASES

if TYPE_CHECKING:
    from app.game.state import GameState
    from app.rules.plan import Plan

Context = dict[str, Any]
ADDED = "_mana_added"  # the resolution context's record of the mana its last "add" instruction added


def _active(state: GameState, rec: dict[str, Any]) -> bool:
    """Is the effect still keeping this mana as the current step ends?"""
    if rec.get("turn") != state.turn.number:
        return False
    phase = state.turn.phase
    if rec.get("until") == "end_of_combat":
        return phase in COMBAT_PHASES and phase != "end_combat"
    return phase != "cleanup"


def kept(state: GameState, player: str) -> dict[str, int]:
    """How much of each type ``player`` keeps as the current step ends."""
    r = state.rules
    out: dict[str, int] = {}
    if r is None:
        return out
    for rec in r.kept_mana:
        if rec.get("player") == player and _active(state, rec):
            for sym, n in (rec.get("mana") or {}).items():
                out[sym] = out.get(sym, 0) + int(n)
    pool = state.players[player].mana if player in state.players else {}
    return {s: min(n, pool.get(s, 0)) for s, n in out.items() if min(n, pool.get(s, 0)) > 0}


def clamp(state: GameState) -> None:
    """Keep each record within its player's pool (mana was spent or removed: the other mana went
    first). Records that ended or hold nothing are dropped."""
    r = state.rules
    if r is None or not r.kept_mana:
        return
    left: dict[tuple[str, str], int] = {}
    out = []
    for rec in r.kept_mana:
        player = rec.get("player")
        if player not in state.players or rec.get("turn") != state.turn.number:
            continue
        pool = state.players[player].mana
        mana = {}
        for sym, n in (rec.get("mana") or {}).items():
            room = left.setdefault((player, sym), pool.get(sym, 0))
            take = min(int(n), room)
            if take > 0:
                mana[sym] = take
                left[(player, sym)] = room - take
        if mana:
            out.append({**rec, "mana": mana})
    r.kept_mana = out


def empty(plan: Plan) -> bool:
    """500.4 with 106.4: empty every pool except the mana an effect keeps. True when something was
    kept (the caller doesn't empty the pools itself)."""
    state = plan.state
    r = plan.rules
    clamp(state)
    if not r.kept_mana:
        return False
    keep = {p: kept(state, p) for p in state.players}
    if not any(keep.values()):
        r.kept_mana = []
        return False
    for pid, player in state.players.items():
        delta = {s: keep[pid].get(s, 0) - n for s, n in player.mana.items() if n > keep[pid].get(s, 0)}
        if delta:
            plan.do({"type": "rules_mana", "player": pid, "tap": [], "sacrifice": [], "delta": delta, "life": 0,
                     "label": ""}, actor=plan.active)
    r.kept_mana = [rec for rec in r.kept_mana if _active(state, rec)]
    clamp(state)
    return True


def keep(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Until end of turn, you don't lose this mana as steps and phases end": the mana the
    previous instruction of this resolution added (``ctx[ADDED]``) is kept."""
    mana = {s: int(n) for s, n in (ctx.get(ADDED) or {}).items() if int(n) > 0}
    if not mana:
        return True
    pid = ctx["controller"]
    plan.rules.kept_mana.append({"player": pid, "mana": mana, "until": e.get("until", "end_of_turn"),
                                 "turn": plan.state.turn.number})
    clamp(plan.state)
    return True
