"""-- leaving the game (wave MBC-D) -- a player leaving the game as an event, delayed triggers that wait for it, and the objects that
left with that player as they last existed. Researched against CR 2026-09-25 (800.4a, 104.3a, 603.7, 603.10f, 611.2b, 608.2h, 707.2).

**The event.** A player who loses or concedes leaves a multiplayer game (104.3a, 800.4a); the engine carries that out in one place,
``app/rules/leave.py`` ``leave_game`` — whichever way they lost: a state-based action (704.5a-c, app/rules/sba.py), an effect
(app/rules/win_game.py), or a concession (app/rules/engine.py ``concede``). Before anything moves, ``departing`` snapshots every permanent
the player controls (not the phased-out ones, 702.26b: treated as though they don't exist) with ``Plan.freeze_departures`` — their copiable
values (707.2, the layer-1 copy effects included), their types, abilities and power/toughness as they last existed — and emits one
``player_left_game`` event (``player``, ``left_with``). What leave_game does next (their own cards stay on their side of the table as an
inert record, others' cards go back or into exile, tokens cease to exist) can't change what those snapshots say.

A player the host removes from the table (``remove_player``, a table tool) does not lose the game and is not a rules event: nothing here.

**Delayed triggers on it.** A delayed triggered ability (603.7) whose ``when`` is ``{"kind": "player_left", "player": <pid>, "lost": True,
"while_counter": <kind>}`` waits for that player to leave the game (``lost``: having lost or conceded — conceding is losing, 104.3a), "for as
long as they have a <kind> counter" (611.2b: judged as they leave; once the player has no such counter, the ability ends, ``expire``). It
triggers once (603.7c) for its controller, who must still be in the game (800.4a: abilities a departed player controlled cease to exist),
and outlives its source: nothing about the object that created it matters any more. Its event carries the objects that left with the player
(``ObjectRef`` with the snapshot), so "for each artifact and creature they controlled" reads them as they last existed (603.10f looks back,
608.2h), never the record left on the table.

``copy_left`` creates a token that's a copy of each of them (of the given card types as they last existed, 700.4), from those copiable values
(707.2, 111.12) through the token choke point (app/rules/replace.py ``create_token_batch``: a replacement that asks pauses and runs this again;
the snapshots don't change, so the copies don't either). A face-down or double-faced object is left to the players, as for any copy of an
object that is gone (app/rules/populate.py ``recipes_of``). Deterministic: no randomness, the snapshots ride on the recorded rules state.
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DelayedTrigger, ObjectRef, TriggerEvent

if TYPE_CHECKING:
    from app.game.rules_state import Event, ObjectSnapshot
    from app.rules.plan import Plan

Context = dict[str, Any]
KIND = "player_left"


def departing(plan: Plan, player: str) -> list[ObjectSnapshot]:
    """800.4a, before anything leaves: the permanents ``player`` controls as they are now, and the ``player_left_game`` event."""
    from app.game.rules_state import emit

    ids = sorted(c.id for c in plan.state.cards.values() if c.controller == player and c.zone.endswith(":battlefield"))
    frozen = plan.freeze_departures(ids) if ids else None
    snaps = [frozen.snapshots[c] for c in ids if c in frozen.snapshots] if frozen is not None else []
    emit(plan.state, "player_left_game", player=player, left_with=snaps)
    return snaps


def create(plan: Plan, ctx: Context, player: str, effects: list[dict[str, Any]], *, while_counter: str | None = None) -> bool:
    """Create the delayed triggered ability (603.7a) that triggers when ``player`` loses the game; True if it was created. "For as long as they
    have a … counter": a duration already over as it would begin does nothing (611.2b)."""
    if player not in plan.live():
        return False
    if while_counter and plan.state.players[player].resources.get(while_counter, 0) <= 0:
        return False
    when = {"kind": KIND, "player": player, "lost": True, **({"while_counter": while_counter} if while_counter else {})}
    plan.rules.delayed.append(DelayedTrigger(
        id=secrets.token_hex(4), controller=ctx["controller"], source_card=ctx.get("source_card"), source_object=ctx.get("source_object"),
        name=ctx.get("name") or "", when=when, effects=effects, refs={}, turn=plan.state.turn.number, step=plan.state.turn.phase,
        created_step=plan.rules.step_serial))
    plan.note(f"{ctx.get('name') or 'A delayed ability'} will trigger when {plan.name(player)} loses the game"
              + (f", for as long as they have a {while_counter} counter" if while_counter else ""), actor=ctx["controller"])
    return True


def _holds(plan: Plan, t: DelayedTrigger) -> bool:
    counter = t.when.get("while_counter")
    player = plan.state.players.get(t.when.get("player") or "")
    return player is not None and (not counter or player.resources.get(counter, 0) > 0)


def on_events(plan: Plan, events: list[Event]) -> None:
    """The trigger collector's new events (app/rules/triggers.py): a watched player left the game — it triggers (603.7c, once); then the
    ones whose duration is over end (611.2b), and so do those whose controller left (800.4a)."""
    r = plan.rules
    waiting = [t for t in r.delayed if t.when.get("kind") == KIND]
    if not waiting:
        return
    from app.rules import delayed

    done: set[str] = set()
    for e in events:
        if e.kind != "player_left_game" or not e.player or e.manual:
            continue
        lost = e.player in r.lost or e.player in r.conceded
        for t in waiting:
            if t.id in done or t.when.get("player") != e.player:
                continue
            done.add(t.id)  # (it watched this player: left the game, it is over either way)
            if (t.when.get("lost") and not lost) or not _holds(plan, t):
                continue
            objects = [ObjectRef(card=s.card, object_id=s.object_id, zone=s.zone, snapshot=s) for s in e.left_with]
            delayed._fire(plan, t, TriggerEvent(kind="lose_game", batch=e.batch, count=1, players=[e.player], objects=objects))
    live = set(plan.live())
    r.delayed = [t for t in r.delayed if t.when.get("kind") != KIND or (
        t.id not in done and t.controller in live and t.when.get("player") in live and _holds(plan, t))]


# -- resolution ------------------------------------------------------------------------------------------------------------------------
def copy_left(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"For each artifact and creature they controlled, create a token that's a copy of it": the objects of the trigger's event (the
    player's permanents as they left, 800.4a) of those types as they last existed (700.4), copied from their copiable values (707.2, 608.2h)
    by this ability's controller."""
    from app.rules import copying, populate
    from app.rules import replace as replace_
    from app.rules.triggers import _snapshot_card

    types = set(e.get("types") or ())
    snaps = []
    for raw in (ctx.get("event") or {}).get("objects") or []:
        ref = ObjectRef.model_validate(raw)
        if ref.snapshot is None:
            continue
        if not types or types & _snapshot_card(plan, ref.snapshot)[1].types:
            snaps.append(ref.snapshot)
    me = ctx["controller"]
    requests = []
    notes: list[str] = []
    refused: list[str] = []
    for recipe, maker in populate.recipes_of(plan, snaps, lambda _snap: me):
        if isinstance(recipe, str):
            refused.append(recipe)
            continue
        req = copying.token_copy_request(plan, ctx, maker, recipe, 1, notes=notes)
        if req is not None:
            requests.append(req)
    if requests and replace_.create_token_batch(plan, requests, ctx=ctx, bind=None, then=replace_.rerun_then(ctx, e)) is None:
        return False  # (a replacement asks: this instruction runs again with the answer)
    for n in notes:
        plan.note(n, actor=me)
    if not snaps:
        plan.note(f"{ctx.get('name') or 'It'}: they controlled no such permanent — no token is created", actor=me)
    if refused:
        copying._manual(plan, copying.new_job(ctx, controller=me, objects=[], retarget=False, label=ctx.get("name") or "Copy"),
                        f"{ctx.get('name') or 'Copy'}: do this by hand — {'; '.join(refused)} — then press Done")
        return False
    return True


PRIMITIVES: dict[str, Any] = {"copy_left_game": copy_left}
