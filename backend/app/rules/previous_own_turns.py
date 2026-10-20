"""Bounded, public attack facts from each player's most recent completed turn."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.plan import Plan

ATTACK = 'cant_attack_if_attacked_last_own_turn'
UNTAP = 'doesnt_untap_if_attacked_last_own_turn'
DEFENDER = 'attack_despite_defender_last_own'


def attacked(state: GameState, card: CardInstance) -> bool | None:
    rules = state.rules
    if rules is None or card.controller not in rules.own_turn_history_known:
        return None
    summary = rules.completed_own_turns.get(card.controller)
    return summary is not None and rules.object_id(card.id) in summary.attackers


def attacked_player(state: GameState, player: str, protected: str) -> bool | None:
    rules = state.rules
    if rules is None or player not in rules.own_turn_history_known:
        return None
    summary = rules.completed_own_turns.get(player)
    return summary is not None and protected in summary.attacked_players


def eligible_player(state: GameState, protected: str) -> bool:
    return any(pid != protected and not p.left and attacked_player(state, pid, protected) is True
               for pid, p in state.players.items())


def begin(plan: Plan) -> None:
    from app.game.rules_state import initialize_own_turn_history
    from app.rules import scripts

    initialize_own_turn_history(plan.state)
    rules = plan.rules
    if rules.own_turn_history_notice or all(p in rules.own_turn_history_known for p in plan.live()):
        return
    for card in plan.state.cards.values():
        if not card.zone.endswith(':battlefield'):
            continue
        own = scripts.statics(plan.ch(card))
        unknown = card.controller not in rules.own_turn_history_known and bool({ATTACK, UNTAP} & own)
        unknown = unknown or (any(r.startswith(DEFENDER + ':') for r in own)
                              and any(p != card.controller and p not in rules.own_turn_history_known for p in plan.live()))
        if unknown:
            plan.note('Earlier attack history is unavailable in this save. Affected cards use conservative restrictions until those players complete a turn; manual adjustments remain available.')
            rules.own_turn_history_notice = True
            return
