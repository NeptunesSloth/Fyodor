"""A player leaving a multiplayer game (rule 800.4a), after losing or conceding.

Their seat is not simply hidden. In order:

1. everything they *own* leaves the game: their tokens cease to exist, their cards on other
   players' battlefields or on the stack go back to their own (now inert) side of the table;
2. effects that gave them control of other players' objects end: those return to their owners;
3. abilities they controlled on the stack cease to exist;
3b. objects they still control are exiled: another player's card they put onto the battlefield
   under their own control (reanimated "under your control" — no control-changing effect to end)
   or are casting (from another player's graveyard or exile);
4. they are removed from combat (creatures attacking them or their planeswalkers stop attacking)
   and from pending combat decisions;
5. the monarch / initiative pass on (to the active player, or the next player if that's them).

Their own cards stay visible on their side of the table as a record, and the engine ignores them
from then on (``Plan.in_game``). Life totals, commander damage and stats are kept.
"""

from __future__ import annotations

from app.game.state import STACK
from app.rules.plan import Plan


def leave_game(plan: Plan, player: str) -> None:
    state = plan.state
    r = plan.rules
    # The leaver's permanents (wherever they are) leave the game with them: their "until ~ leaves
    # the battlefield" links end (610.3). Captured before anything moves.
    leaving = {plan.oid(c) for c in state.cards.values() if c.owner == player and c.zone.endswith(":battlefield")}
    for card in list(state.cards.values()):
        if card.id not in state.cards:
            continue
        zone = card.zone.rsplit(":", 1)[-1]
        on_own_side = card.zone.startswith(f"{player}:")
        if card.owner == player and (card.is_token or card.ability is not None):
            plan.do({"type": "delete_card", "card_ids": [card.id], "force": True}, actor=player)
        elif card.owner == player and not on_own_side:
            dest = "battlefield" if zone == "battlefield" else "graveyard" if card.zone == STACK else zone
            plan.do({"type": "move", "card_ids": [card.id], "to": {"player": player, "zone": dest}}, actor=player)
        elif card.owner != player and card.controller == player:
            if card.ability is not None:
                plan.do({"type": "delete_card", "card_ids": [card.id], "force": True}, actor=player)  # 800.4a
            elif card.owner not in plan.live():
                continue  # (it left the game with its own owner already)
            elif zone in ("battlefield", "phased") and _control_changed(plan, card.id):
                plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": zone}},
                        actor=player)  # the control-changing effect ends (-- review (wave 14R) -- phased out: 702.26n, it phases
                # in later, here with its owner's next untap step)
            elif zone in ("battlefield", "phased") or card.zone == STACK:  # 800.4a: still controlled by them: exiled
                plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": "exile"}},
                        actor=player)
    _end_linked(plan, leaving)
    gone = {player} | {cid for cid, c in state.cards.items() if c.controller == player and c.zone.endswith(":battlefield")}
    stop = [c.id for c in state.cards.values() if c.attacking is not None and c.attacking.id in gone]
    if stop:
        plan.do({"type": "attack", "card_ids": stop, "target": None}, actor=state.cards[stop[0]].controller)
    r.blockers_pending = [p for p in r.blockers_pending if p != player]
    r.passed = [p for p in r.passed if p != player]
    if r.payment_outer is not None and r.payment_outer.player == player:  # (review 28D: a payment a nested choice set aside: theirs too)
        r.payment_outer = None
    if r.decision is not None and r.decision.player == player:
        r.decision = None
    if r.priority == player:
        r.priority = None
    successor = plan.active if plan.active != player else plan.after(player)
    if state.table.monarch == player:
        from app.rules.effects import can_become_monarch

        for _ in plan.live():  # (-- cant restrictions (wave 46A) -- 725.4: the next player in turn order who can become the monarch)
            if successor != player and can_become_monarch(plan, successor):
                plan.do({"type": "set_monarch", "player": successor}, actor=successor)
                break
            successor = plan.after(successor)
    if state.table.initiative == player:
        plan.do({"type": "set_initiative", "player": successor}, actor=successor)
    plan.note(f"{plan.name(player)} has left the game")


def _control_changed(plan: Plan, card_id: str) -> bool:
    """800.4a: does the leaver control this permanent through a control-changing effect (which
    ends), rather than because it entered the battlefield under their control (then it's exiled)?
    Unknown (an older save, automation turned on mid-game): a control change, as before."""
    mark = plan.rules.controlled_since.get(card_id)
    return mark is None or mark.changed is not False


def _end_linked(plan: Plan, leaving: set[str]) -> None:
    """610.3: "exile … until ~ leaves the battlefield" — a source the leaver owned left the game
    with them (800.4a), so what it exiled returns now (to its owners still in the game). The
    leaver's own cards in exile have left the game too and stay put. A source taken out of
    automation (per-card MANUAL) is left to the players, as when it leaves the battlefield
    (app/rules/triggers.py). "For as long as …" durations whose source left this way end with
    the next check (app/rules/delayed.expire)."""
    from app.rules import attachments
    from app.rules.effects import linked_entries  # (effects imports this module's callers)

    entries = []
    for key in [k for k in plan.rules.linked_exile if k in leaving]:
        if plan.rules.card_mode(key.rsplit(".", 1)[0]) != "manual":
            entries += linked_entries(plan, key)
    if entries:
        attachments.enter(plan, entries, None)  # all at once (610.3d); an Aura may ask what it enchants
