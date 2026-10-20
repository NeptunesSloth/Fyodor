"""Bind protection qualities to the players named by a resolving effect (702.16k)."""
from __future__ import annotations

from typing import Any

from app.rules.plan import Plan

OPPONENTS = 'Protection from each of your opponents'


def abilities(plan: Plan, ctx: dict[str, Any], lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        if line.rstrip('.') == OPPONENTS:
            out.extend(f'Protection from player {p}' for p in plan.live() if p != ctx['controller'])
        else:
            out.append(line)
    return out


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    if body != 'Target opponent takes an extra turn after this one. Until your next turn, you and planeswalkers you control gain protection from that player.':
        return None
    return ([{'do': 'extra_turn', 'who': 'target', 'n': 1},
             {'do': 'player_protection_grant', 'players': 'target', 'player_shield': True,
              'who': 'planeswalkers_you_control', 'duration': 'next_turn'}], 'opponent', False)


def grant(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, layers, player_shields

    players = effects._players(plan, ctx, e['players'])
    cards = ([c.id for c in plan.state.cards.values() if c.zone.endswith(':battlefield')
              and c.controller == ctx['controller'] and 'Planeswalker' in plan.ch(c).types]
             if e['who'] == 'planeswalkers_you_control' else effects._cards(plan, ctx, e['who']))
    duration = e.get('duration', 'end_of_turn')
    if cards and players:
        layers.add_effect(plan, affected=[plan.oid(c) for c in cards], layer='6', source=ctx.get('source_object'),
                          controller=ctx['controller'], duration=duration,
                          add_abilities=[f'Protection from player {p}' for p in players],
                          until_player=ctx['controller'] if duration == 'next_turn' else None,
                          turn=plan.state.turn.number,
                          label='Protection from the chosen player')
    if e.get('player_shield'):
        for player in players:
            player_shields._add(plan, ctx, 'protection', f'player:{player}',
                                'next_turn' if duration == 'next_turn' else 'turn')
    return True


PRIMITIVES = {'player_protection_grant': grant}
