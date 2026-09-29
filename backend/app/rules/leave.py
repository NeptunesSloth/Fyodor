"""A player leaving a multiplayer game (rule 800.4a), after losing or conceding.

Their seat is not simply hidden. In order:

1. everything they *own* leaves the game: their tokens cease to exist, their cards on other
   players' battlefields or on the stack go back to their own (now inert) side of the table;
2. effects that gave them control of other players' objects end: those return to their owners;
3. abilities they controlled on the stack cease to exist;
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
            elif zone == "battlefield" and card.owner in plan.live():
                plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": "battlefield"}},
                        actor=player)  # the control-changing effect ends
            elif card.zone == STACK:
                plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": "exile"}},
                        actor=player)
    gone = {player} | {cid for cid, c in state.cards.items() if c.controller == player and c.zone.endswith(":battlefield")}
    stop = [c.id for c in state.cards.values() if c.attacking is not None and c.attacking.id in gone]
    if stop:
        plan.do({"type": "attack", "card_ids": stop, "target": None}, actor=state.cards[stop[0]].controller)
    r.blockers_pending = [p for p in r.blockers_pending if p != player]
    r.passed = [p for p in r.passed if p != player]
    if r.decision is not None and r.decision.player == player:
        r.decision = None
    if r.priority == player:
        r.priority = None
    successor = plan.active if plan.active != player else plan.after(player)
    if state.table.monarch == player:
        plan.do({"type": "set_monarch", "player": successor}, actor=successor)
    if state.table.initiative == player:
        plan.do({"type": "set_initiative", "player": successor}, actor=successor)
    plan.note(f"{plan.name(player)} has left the game")
