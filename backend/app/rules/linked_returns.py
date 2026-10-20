"""Linked retrieval uses native moves and exact destination outcomes."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_ASMODEUS = "return all cards exiled with ~ to their owner's hand and you lose that much life"
_BAG = "roll a d10. return up to x cards from among cards exiled with ~ to their owners' hands, where x is the result"
_GHOST = ("put each creature card exiled with ~ onto the battlefield under your control with a flying counter on it. "
          "each of them is a 1/1 spirit in addition to its other types")
_PINNACLE = ("put each card exiled with ~ into its owner's graveyard, then create a 2/2 colorless robot artifact creature token "
             "for each card put into a graveyard this way. sacrifice ~")


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import selectors

    text = re.sub(r'\s+', ' ', body).strip().rstrip('.').lower()
    if text == _ASMODEUS:
        return [{'do': 'return_card', 'who': 'exiled_with', 'to': 'hand', 'as': 'linked_return'},
                {'do': 'linked_return_outcome', 'zone': 'hand', 'mode': 'life'}], None, False
    if text == _BAG:
        return [{'do': 'roll', 'sides': 10, 'count': 1},
                {'do': 'return_choice', 'who': 'exiled_with', 'to': 'hand', 'n': {'die': 'result'},
                 'upto': True, 'random': False, 'label': 'card'}], None, False
    if text == 'exile a card from the top of your library face down for each opponent you have':
        return [{'do': 'exile_top', 'who': 'you', 'n': {'opponents': 1}, 'face_down': True, 'blind': True}], None, False
    if text == _GHOST:
        sel = selectors.parse('creature card')
        assert sel is not None
        return [{'do': 'return_card', 'who': 'exiled_with:' + sel.key(), 'to': 'battlefield', 'under': 'you',
                 'counter': 'flying', 'counter_n': 1, 'tapped': False, 'as': 'linked_return'},
                {'do': 'become', 'who': 'ref:linked_return', 'types': [], 'retain': True, 'add_creature_types': ['Spirit'],
                 'p': 1, 't': 1, 'duration': 'permanent'}], None, False
    if text == _PINNACLE:
        return [{'do': 'return_card', 'who': 'exiled_with', 'to': 'graveyard', 'as': 'linked_return'},
                {'do': 'linked_return_outcome', 'zone': 'graveyard', 'mode': 'robot'},
                {'do': 'sacrifice', 'who': 'self'}], None, False
    return None


def outcome(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, this_way

    n = this_way.count(plan, ctx, {'ref_count': 'linked_return', 'this_way': 'returned' if e['zone'] == 'hand' else 'graveyard', 'of': None})
    if e['mode'] == 'life':
        return effects.lose_life(plan, ctx, {'who': 'you', 'n': n})
    return effects.create_token(plan, ctx, {'who': 'you', 'n': n,
        'token': {'name': 'Robot', 'power': '2', 'toughness': '2', 'colors': [], 'type_line': 'Token Artifact Creature — Robot'}})


PRIMITIVES = {'linked_return_outcome': outcome}
