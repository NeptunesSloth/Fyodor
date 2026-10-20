"""Combat sacrifice mana and a shared one-card exile permission."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if ability.kind == 'triggered' and text == ('Whenever ~ attacks, you may sacrifice another creature. If you do, '
            "add an amount of {R} equal to the sacrificed creature's power. Until end of combat, you don't lose this mana as steps end."):
        base = scripts.define(replace(ability, text='Whenever ~ attacks, you may sacrifice another creature. If you do, draw a card.'), ch)
        if base is not None:
            return {**base, 'effects': [base['effects'][0], {**base['effects'][1], 'skip': 2},
                {'do': 'add_mana', 'sym': 'R', 'n': {'power': 'ref:pay0'}},
                {'do': 'keep_mana', 'until': 'end_of_combat'}]}
    if ability.kind == 'activated' and text == ("{6}: Exile the top card of each opponent's library. Until end of turn, "
            'you may play one of those cards without paying its mana cost.'):
        base = scripts.define(replace(ability, text='{6}: Draw a card.'), ch)
        return {**base, 'effects': [{'do': 'ozai_top_packet'}]} if base is not None else None
    return None


def top_packet(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import exile_packet_continuations as packets

    descriptor = {'binding': 'ref:ozai'}
    opponents = [p for p in plan.state.seat_order if p in plan.live() and p != ctx['controller']]
    packets.top_packet(plan, ctx, descriptor, opponents)
    return packets.insert(ctx, [packets.grant(descriptor, play=True, free=True, limit=1)])


PRIMITIVES = {'ozai_top_packet': top_packet}
