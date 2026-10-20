"""Kicker alternatives and follow-ups composed from native spell primitives."""
from __future__ import annotations

from typing import Any


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = body.strip().rstrip('.')
    separator = '. If this spell was kicked, '
    if separator not in text:
        return None
    first, follow = text.split(separator, 1)
    from app.rules import scripts

    if first == 'Scry 2, then draw a card' and follow == 'you may put a land card from your hand onto the battlefield':
        base = scripts.parse_effects(first + '.')
        extra = scripts.parse_effects(follow[:1].upper() + follow[1:] + '.')
        if base is not None and extra is not None and extra[1] is None:
            tail = [{'do': 'may_rest'}, *extra[0]]
            return [*base[0], {'do': 'kicked_gate', 'kicked': True, 'n': len(tail)}, *tail], base[1], False
    if first == 'Target opponent loses half their life, rounded up' and follow == 'you gain life equal to the life lost this way':
        base = scripts.parse_effects(first + '.')
        if base is not None:
            binding = 'kicked_loss'
            return [{**base[0][0], 'bind': binding},
                    {'do': 'kicked_gate', 'kicked': True, 'n': 1},
                    {'do': 'gain_life', 'who': 'you', 'n': {'ref_amount': binding}}], base[1], False
    if first == 'Return target creature card from your graveyard to your hand' and follow == 'instead put that card onto the battlefield tapped':
        base = scripts.parse_effects(first + '.')
        if base is not None:
            return [{'do': 'kicked_gate', 'kicked': False, 'n': 1}, *base[0],
                    {'do': 'kicked_gate', 'kicked': True, 'n': 1},
                    {**base[0][0], 'to': 'battlefield', 'tapped': True}], base[1], False
    if first == 'Search your library for a basic land card, reveal it, put it into your hand, then shuffle' and follow == 'search your library for two basic land cards instead of one':
        base = scripts.parse_effects(first + '.')
        extra = scripts.parse_effects('Search your library for up to two basic land cards, reveal them, put them into your hand, then shuffle.')
        if base is not None and extra is not None:
            return [{'do': 'kicked_gate', 'kicked': False, 'n': 1}, *base[0],
                    {'do': 'kicked_gate', 'kicked': True, 'n': 1}, *extra[0]], None, False
    if first == 'Target creature gets -2/-2 until end of turn' and follow == 'that creature gets an additional -1/-1 until end of turn for each instant and sorcery card in your graveyard':
        base = scripts.parse_effects(first + '.')
        extra = scripts.parse_effects('Target creature gets -X/-X until end of turn, where X is the number of instant and sorcery cards in your graveyard.')
        if base is not None and extra is not None:
            return [*base[0], {'do': 'kicked_gate', 'kicked': True, 'n': 1}, *extra[0]], base[1], False
    if first == 'Target creature you control deals damage equal to its power to target creature an opponent controls' and follow == 'the creature you control deals twice that much damage instead':
        base = scripts.parse_effects(first + '.')
        if base is not None:
            damage = base[0][0]
            return [{'do': 'kicked_gate', 'kicked': False, 'n': 1}, damage,
                    {'do': 'kicked_gate', 'kicked': True, 'n': 1},
                    {**damage, 'n': {'times': [2, damage['n']]}}], base[1], False
    return None
