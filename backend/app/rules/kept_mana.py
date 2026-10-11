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

Wave 18B: kept mana with a spending restriction (Klauth, Karn, Legacy Reforged) is a pool unit
(app/rules/mana_units.py): the record names its unit ids (``units``) and keeps exactly those.

Refused (the card stays manual): "Players don't lose unspent mana" statics (Upwelling), and amounts
the grammar doesn't read.
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


def kept_units(state: GameState, player: str) -> list[int]:
    """-- mana provenance (wave 18B) -- the pool units ``player`` keeps as the current step ends."""
    r = state.rules
    if r is None or player not in state.players:
        return []
    ids = {i for rec in r.kept_mana if rec.get("player") == player and _active(state, rec) for i in rec.get("units") or []}
    return [u.id for u in state.players[player].mana_units if u.id in ids]


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
        units = [i for i in rec.get("units") or [] if i in {u.id for u in state.players[player].mana_units}]
        for sym, n in (rec.get("mana") or {}).items():
            room = left.setdefault((player, sym), pool.get(sym, 0))
            take = min(int(n), room)
            if take > 0:
                mana[sym] = take
                left[(player, sym)] = room - take
        if mana or units:
            out.append({**rec, "mana": mana, "units": units})
    r.kept_mana = out


def _always(plan: Plan) -> dict[str, set[str]]:
    """-- static_other sweep (wave 21A) -- 106.4: the colors each player never loses as steps and phases end (statics of their permanents)."""
    from app.rules.cast_limits import _statics

    out: dict[str, set[str]] = {}
    for src, d in _statics(plan.state, plan.info, "keep_mana"):
        out.setdefault(src.controller, set()).add(d["color"])
    return out


def _colorless(plan: Plan) -> set[str]:
    """-- unspent mana (wave 35C) -- 614.1a: the players with "If you would lose unspent mana, that mana becomes colorless instead." (Kruphix, Omnath,
    Horizon Stone). Several of them agree on what happens, so there is no 616.1 order to ask."""
    from app.rules.cast_limits import _statics

    return {src.controller for src, _ in _statics(plan.state, plan.info, "colorless_mana")}


def _to_colorless(plan: Plan, pid: str, keep: dict[str, int], keep_u: list[int]) -> None:
    """-- unspent mana (wave 35C) -- 500.4 / 614.1a: what ``pid`` would lose (the pool but the mana an effect keeps) stays in the pool as colorless mana;
    restrictions and riders stay with it (the Gatherer rulings of Kruphix, Omnath, Horizon Stone), so a unit keeps all but its type."""
    player = plan.state.players[pid]
    delta = {s: keep.get(s, 0) - n for s, n in player.mana.items() if s != "C" and n > keep.get(s, 0)}
    changed = [u for u in player.mana_units if u.id not in keep_u and u.sym != "C"]
    if not delta and not changed:
        return
    if delta:
        delta["C"] = -sum(delta.values())
    plan.do({"type": "rules_mana", "player": pid, "tap": [], "sacrifice": [], "delta": delta, "life": 0, "spend_units": [u.id for u in changed],
             "add_units": [{**u.model_dump(exclude={"id"}), "sym": "C"} for u in changed], "label": ""}, actor=plan.active)


def empty(plan: Plan) -> bool:
    """500.4 with 106.4: empty every pool except the mana an effect keeps. True when something was
    kept (the caller doesn't empty the pools itself)."""
    state = plan.state
    r = plan.rules
    clamp(state)
    always = _always(plan)
    colorless = _colorless(plan)
    if not r.kept_mana and not always and not colorless:
        return False
    keep = {p: kept(state, p) for p in state.players}
    keep_u = {p: kept_units(state, p) for p in state.players}
    for pid, colors in always.items():  # -- static_other sweep (wave 21A) -- "You don't lose unspent red mana as steps and phases end."
        pool = state.players[pid]
        keep[pid].update({c: pool.mana[c] for c in colors if pool.mana.get(c)})
        keep_u[pid] = sorted({*keep_u[pid], *(u.id for u in pool.mana_units if u.sym in colors)})
    if not any(keep.values()) and not any(keep_u.values()) and not colorless:
        r.kept_mana = []
        return False
    for pid in colorless:  # (-- unspent mana (wave 35C) -- the colorless mana stays: nothing of theirs is lost)
        _to_colorless(plan, pid, keep[pid], keep_u[pid])
        keep[pid] = {s: n for s, n in state.players[pid].mana.items()}
        keep_u[pid] = [u.id for u in state.players[pid].mana_units]
    for pid, player in state.players.items():
        delta = {s: keep[pid].get(s, 0) - n for s, n in player.mana.items() if n > keep[pid].get(s, 0)}
        if delta or len(keep_u[pid]) < len(player.mana_units):  # (units: wave 18B, the rest of them empty)
            plan.do({"type": "rules_mana", "player": pid, "tap": [], "sacrifice": [], "delta": delta, "life": 0,
                     "empty_units": True, "keep_units": keep_u[pid], "label": ""}, actor=plan.active)
    r.kept_mana = [rec for rec in r.kept_mana if _active(state, rec)]
    clamp(state)
    return True


def keep(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Until end of turn, you don't lose this mana as steps and phases end": the mana the
    previous instruction of this resolution added (``ctx[ADDED]``) is kept."""
    mana = {s: int(n) for s, n in (ctx.get(ADDED) or {}).items() if int(n) > 0}
    units = list(ctx.get("_mana_unit_ids") or ())  # (wave 18B: mana_units.restrict made the mana added into units)
    if not mana and not units:
        return True
    pid = ctx["controller"]
    plan.rules.kept_mana.append({"player": pid, "mana": mana, "units": units, "until": e.get("until", "end_of_turn"),
                                 "turn": plan.state.turn.number})
    clamp(plan.state)
    return True
